"""Layer 5 dashboard - service layer (models + feature extraction).
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from ._paths import ML_ROOT
from .config import SNAPSHOT_MANIFEST, SNAPSHOT_PARQUET
from models.phase5.dashboard.backend.features import (
    extract_features, latest_anchor, load_segments, load_wes,
)
from .subgroup_policy import subgroup_flags

ROOT = ML_ROOT
DEG_DIR = ROOT / "models" / "phase5" / "serving" / "degradation"
PTURN_DIR = ROOT / "models" / "phase5" / "serving" / "turn_probability"
SEG = ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet"
TURNS = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
TRAJ_ARTEFACT = ROOT / "models" / "experiments" / "v5" / "trajectory_product_analysis.json"

HORIZONS = (30, 90, 180)
DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
WEAR_DIMS = ("wsmRoot", "wsmFlange", "wsmThread")
WEAR_BETTER_TOL = 0.05      # mm threshold below current to flag "wear improves"
DIA_INC_TOL = 0.001         # mm; predicted diameter above current
DAY = np.timedelta64(1, "D")

# Condemning limit register. Only wsmDia has an approved numeric hard stop
# (domain constant 1016 mm, lower is worse). Flange/root/tread action limits
# are NOT approved yet -> limit_mm stays None and time-to-limit is not computed.
CONDEMNING_DIA_MM = 1016.0
LIMIT_REGISTER = {
    "wsmDia": {"limit_mm": CONDEMNING_DIA_MM, "direction": "down",
               "label": "condemning (dia)"},
    "wsmFlange": None,
    "wsmRoot": None,
    "wsmThread": None,
}
TTL_HORIZONS = (30, 90, 180)


@lru_cache(maxsize=1)
def degradation_models() -> dict:
    feats = json.loads((DEG_DIR / "features.json").read_text())
    enc = joblib.load(DEG_DIR / "encoder.joblib")
    models = {}
    for dim in DIMM:
        for h in HORIZONS:
            models[(dim, h)] = joblib.load(DEG_DIR / f"model_{dim}_{h}d.joblib")
    return {"models": models, "enc": enc, "num_feats": feats["num_feats"],
            "cat_feats": feats["cat_feats"]}


@lru_cache(maxsize=1)
def pturn_models() -> dict:
    feats = json.loads((PTURN_DIR / "features.json").read_text())
    enc = joblib.load(PTURN_DIR / "encoder.joblib")
    models = {h: joblib.load(PTURN_DIR / f"model_{h}d.joblib") for h in feats["horizons"]}
    manifest = json.loads((PTURN_DIR / "manifest.json").read_text())
    rate = {m["horizon"]: m["turn_rate_train"] for m in manifest["models"]}
    return {"models": models, "enc": enc, "num_feats": feats["num_feats"],
            "cat_feats": feats["cat_feats"], "turn_rate_train": rate}


def _artifact_version() -> str:
    """Deterministic serving-model version from the on-disk artifacts.

    A content hash of the feature schema + manifest (+ model file sizes so a
    retrained model bumps the version). Short enough for a footnote, stable
    across restarts, and changes whenever the artifacts change.
    """
    parts = []
    for f in ("features.json", "manifest.json"):
        p = DEG_DIR / f
        parts.append(p.read_bytes() if p.exists() else b"")
    for dim in DIMM:
        for h in HORIZONS:
            p = DEG_DIR / f"model_{dim}_{h}d.joblib"
            parts.append(str(p.stat().st_size).encode() if p.exists() else b"")
    return hashlib.sha256(b"|".join(parts)).hexdigest()[:10]


def degradation_meta() -> dict:
    """Model version, train cutoff and target mode for the degradation service."""
    feats = json.loads((DEG_DIR / "features.json").read_text())
    mf = json.loads((DEG_DIR / "manifest.json").read_text())
    targets = {m["target"] for m in mf.get("models", [])}
    return {
        "model_version": _artifact_version(),
        "train_cutoff": feats.get("train_cutoff"),
        "n_train": feats.get("n_train_rows"),
        "target_mode": "delta" if targets == {"delta"} else "level",
        "task": mf.get("task"),
    }


def feature_coverage(feat: dict, num_feats: list[str]) -> float | None:
    """Share of numeric serving inputs that are present and finite (0..1)."""
    if not num_feats:
        return None
    present = 0
    for c in num_feats:
        v = feat.get(c)
        if v is not None and not pd.isna(v) and np.isfinite(float(v)):
            present += 1
    return round(present / len(num_feats), 4)


def validate_serving() -> list[str]:
    """Fail-fast check of the serving artifacts at load (not request time).

    Raises RuntimeError on a missing file / malformed schema so a broken
    deployment surfaces at startup, not as a KeyError on the first request.
    Returns a list of warnings (non-fatal, e.g. unknown dims in manifest).
    """
    warnings: list[str] = []
    for name, d, feats_key, dims, horizons in (
        ("degradation", DEG_DIR, "num_feats", DIMM, HORIZONS),
        ("turn_probability", PTURN_DIR, "num_feats", None, None),
    ):
        feats_p = d / "features.json"
        man_p = d / "manifest.json"
        if not feats_p.exists():
            raise RuntimeError(f"[{name}] missing features.json: {feats_p.relative_to(ROOT)}")
        if not man_p.exists():
            raise RuntimeError(f"[{name}] missing manifest.json: {man_p.relative_to(ROOT)}")
        feats = json.loads(feats_p.read_text())
        for key in ("num_feats", "cat_feats"):
            if key not in feats or not feats[key]:
                raise RuntimeError(f"[{name}] features.json missing/empty {key}")
        if "train_cutoff" not in feats:
            warnings.append(f"[{name}] features.json has no train_cutoff")
        if not (d / "encoder.joblib").exists():
            raise RuntimeError(f"[{name}] missing encoder.joblib")
        manifest = json.loads(man_p.read_text())
        models = manifest.get("models", [])
        if not models:
            raise RuntimeError(f"[{name}] manifest has no models")
        for m in models:
            if not (d / m["path"]).exists():
                raise RuntimeError(f"[{name}] manifest model missing: {m['path']}")
        if name == "degradation":
            have = {(m["dim"], int(m["horizon"])) for m in models}
            want = {(dim, h) for dim in DIMM for h in HORIZONS}
            missing = want - have
            if missing:
                raise RuntimeError(f"[degradation] manifest missing models: {sorted(missing)}")
    return warnings


def capabilities() -> dict:
    """Feature flags for the UI. `p0_2_dia_fix` gates forecast rendering."""
    try:
        meta = degradation_meta()
    except Exception:
        meta = {}
    return {
        "p0_2_dia_fix": meta.get("target_mode") == "delta",
        "degradation_serving": {
            "model_version": meta.get("model_version"),
            "train_cutoff": meta.get("train_cutoff"),
            "n_train": meta.get("n_train"),
            "target_mode": meta.get("target_mode"),
        },
    }


def _feature_vector(feat_row: dict, num_feats, cat_feats, enc) -> np.ndarray:
    Xn = np.array([[feat_row.get(c, np.nan) for c in num_feats]], dtype=float)
    cat = np.array([[str(feat_row.get(c, "NA")) if feat_row.get(c) is not None
                     and not pd.isna(feat_row.get(c)) else "NA"
                     for c in cat_feats]])
    Xc = enc.transform(cat)
    return np.hstack([Xn, Xc])


def predict_degradation(wheelset_id: int, anchor=None) -> dict:
    if anchor is None:
        anchor = latest_anchor(wheelset_id)
    if anchor is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "forecasts": []}
    fr = extract_features(wheelset_id, anchor)
    if fr is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": anchor, "forecasts": []}
    svc = degradation_models()
    meta = degradation_meta()
    cov = feature_coverage(fr, svc["num_feats"])
    X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
    fc = []
    for dim in DIMM:
        current = fr.get(f"mean_{dim}")
        for h in HORIZONS:
            m = svc["models"][(dim, h)]
            delta = float(m.predict(X)[0])
            # Serving models regress delta (tgt - anchor); reconstruct the
            # level for display so the forecast is an absolute profile state.
            value = None
            if np.isfinite(delta) and current is not None and np.isfinite(current):
                value = round(current + delta, 4)
            width = _conformal_width_mm(dim, h)
            flags = _physics_flags(dim, current, value)
            fc.append({"horizon": h, "dim": dim, "value": value,
                       "delta": round(delta, 4) if np.isfinite(delta) else None,
                       "current": round(float(current), 4)
                       if current is not None and np.isfinite(current) else None,
                       "low": round(value - width, 4) if value is not None and width is not None else None,
                       "high": round(value + width, 4) if value is not None and width is not None else None,
                       "implausibility_flag": flags[0] if flags else None,
                       "model_version": meta.get("model_version"),
                       "train_cutoff": meta.get("train_cutoff"),
                       "feature_coverage": cov,
                       "subgroup_flags": subgroup_flags(fr, dim, h)})
    return {"wheelset_equipment_id": wheelset_id, "anchor": anchor,
            "model": meta, "feature_coverage": cov, "forecasts": fc}


def predict_pturn(wheelset_id: int, anchor=None) -> dict:
    if anchor is None:
        anchor = latest_anchor(wheelset_id)
    if anchor is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "probabilities": []}
    fr = extract_features(wheelset_id, anchor)
    if fr is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": anchor, "probabilities": []}
    svc = pturn_models()
    X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
    out = []
    for h in svc["models"]:
        m = svc["models"][h]
        p = float(m.predict_proba(X)[0, 1])
        out.append({"horizon": h, "probability": round(p, 4),
                    "turn_rate_train": svc["turn_rate_train"].get(h)})
    return {"wheelset_equipment_id": wheelset_id, "anchor": anchor,
            "probabilities": out}


@lru_cache(maxsize=1)
def trajectory_artefact() -> dict:
    if not TRAJ_ARTEFACT.exists():
        return {}
    return json.loads(TRAJ_ARTEFACT.read_text())


def _conformal_width_mm(dim: str, h: int) -> float | None:
    a = trajectory_artefact()
    try:
        return float(a["3_conformal_80pct"][dim][f"{h}d"]["conformal_width_mm"])
    except (KeyError, TypeError):
        return None


def _noise_floor_mm(dim: str) -> float | None:
    a = trajectory_artefact()
    try:
        return float(a["2_noise_floor"][dim]["central_sigma_mm"])
    except (KeyError, TypeError):
        return None


def _crossing_days(times: list[int], values: list[float | None],
                   limit: float, direction: str) -> float | None:
    """First day a piecewise-linear (t, value) path crosses `limit`.

    direction "down": value falls to the limit (dia shrinks to 1016).
    direction "up":   value rises to the limit (root/tread grow to 3mm, TBD).
    Returns None if the limit is not crossed within the provided times.
    """
    first = True
    prev_t = prev_v = None
    for t, v in zip(times, values):
        if v is None or not np.isfinite(v):
            first = True
            prev_t = prev_v = None
            continue
        if not first and prev_v is not None and prev_t is not None:
            lo_v, hi_v = sorted((prev_v, v))
            if direction == "down" and lo_v <= limit <= hi_v:
                # interpolate when the falling edge crosses
                if v != prev_v:
                    frac = (prev_v - limit) / (prev_v - v)
                    return float(prev_t + frac * (t - prev_t))
            elif direction == "up" and lo_v <= limit <= hi_v:
                if v != prev_v:
                    frac = (limit - prev_v) / (v - prev_v)
                    return float(prev_t + frac * (t - prev_t))
        first = False
        prev_t, prev_v = t, v
    return None


def _time_to_limit(dim: str, cur: float | None,
                   pred: dict, low: dict, high: dict) -> dict | None:
    """Time-to-limit for one dim from anchor + 30/90/180 forecasts.

    Builds three piecewise-linear paths (point, interval-lo, interval-hi) over
    the horizon grid and finds the first crossing of the approved limit. Only
    wsmDia has an approved limit; other dims return None until engineering
    signs off numeric thresholds.
    """
    reg = LIMIT_REGISTER.get(dim)
    if reg is None or cur is None or not np.isfinite(cur):
        return None
    ttl: dict = {
        "dim": dim,
        "limit_mm": reg["limit_mm"],
        "direction": reg["direction"],
        "label": reg["label"],
        "current_mm": round(float(cur), 4),
        "predicted_at": {}, "interval_lo": {}, "interval_hi": {},
        "days_to_limit_point": None,
        "days_to_limit_lo": None,
        "days_to_limit_hi": None,
        "status": "beyond_horizon",
        "note": ("days-to-condemning from serving delta forecasts at "
                 "30/90/180; piecewise-linear; hard stop 1016 mm (dia). "
                 "Conformal bands are calibrated for flange/root/tread only, "
                 "so the dia band (interval_lo/hi) is not reported until a "
                 "dia conformal width is calibrated; only the point path is "
                 "used for the dia hard stop. Flange/root/tread limits are "
                 "not approved."),
    }
    times = list(TTL_HORIZONS)
    for h in TTL_HORIZONS:
        p = pred.get(h)
        ttl["predicted_at"][h] = round(float(p), 4) if p is not None and np.isfinite(p) else None
        ttl["interval_lo"][h] = round(float(low[h]), 4) if low.get(h) is not None and np.isfinite(low[h]) else None
        ttl["interval_hi"][h] = round(float(high[h]), 4) if high.get(h) is not None and np.isfinite(high[h]) else None

    limit = reg["limit_mm"]
    direction = reg["direction"]

    # Already at/beyond the limit now
    if (direction == "down" and cur <= limit) or (direction == "up" and cur >= limit):
        ttl["days_to_limit_point"] = 0.0
        ttl["days_to_limit_lo"] = 0.0
        ttl["days_to_limit_hi"] = 0.0
        ttl["status"] = "at_limit"
        return ttl

    point = _crossing_days([0] + times, [cur] + [pred.get(h) for h in times], limit, direction)
    lo = _crossing_days([0] + times, [cur] + [low.get(h) for h in times], limit, direction)
    hi = _crossing_days([0] + times, [cur] + [high.get(h) for h in times], limit, direction)

    ttl["days_to_limit_point"] = round(point, 1) if point is not None else None
    # conservative edge = whichever band edge reaches the limit sooner
    edges = [d for d in (lo, hi) if d is not None]
    if edges:
        ttl["days_to_limit_lo"] = round(min(edges), 1)
        ttl["days_to_limit_hi"] = round(max(edges), 1) if len(edges) > 1 else None
    if point is not None:
        ttl["status"] = "within_horizon"
    return ttl


def operational_capture() -> dict:
    """Read operational capture@k from the trajectory artefact (turn-within-H proxy).

    Success = wheelset turned within H days (confirmed lifecycle post_ts in
    (t, t+H]); ranked by predicted delta for the dim at horizon H. Censored
    anchors (no turn AND no later measurement) are dropped. capture@1/5/10% =
    share of turned wheelsets found in the top k% by predicted delta.
    """
    a = trajectory_artefact().get("4_operational_capture", {})
    by_dim = {}
    for dim, horizons in a.items():
        by_dim[dim] = {}
        for h, cell in horizons.items():
            if cell is None:
                continue
            by_dim[dim][h] = {
                "n_label": int(cell.get("n_label", 0)),
                "turn_rate": cell.get("turn_rate"),
                "capture": {k: v for k, v in cell.items()
                            if k.startswith("capture_")},
            }
    return {
        "task": "operational capture@k (flange/root/tread)",
        "source": "trajectory_product_analysis.json $4",
        "label": ("share of wheelsets turned within H days captured in the top k% "
                  "ranking by predicted delta"),
        "by_dim": by_dim,
        "note": ("Proxy from the trajectory artefact: label = confirmed lifecycle "
                 "turn completes within (t, t+H]; censored anchors dropped. "
                 "Turn-within-H is shed-maintenance behaviour, NOT an engineering "
                 "failure threshold — it never ranks wheelsets on its own."),
    }


def _delta_metrics_slim() -> dict:
    a = trajectory_artefact().get("1_delta_metrics", {})
    out = {}
    for dim, hs in a.items():
        out[dim] = {f"{h}d": {
            "mae_mm": m.get("mae_mm"),
            "delta_r2": m.get("delta_r2"),
            "delta_spearman": m.get("delta_spearman"),
        } for h, m in hs.items()}
    return out


def _physics_flags(dim: str, current: float | None, predicted: float | None) -> list[str]:
    if predicted is None or current is None or not np.isfinite(current) or not np.isfinite(predicted):
        return []
    if dim == "wsmDia" and predicted > current + DIA_INC_TOL:
        return ["increasing_diameter"]
    if dim in WEAR_DIMS and predicted < current - WEAR_BETTER_TOL:
        return ["wear_better_than_current"]
    return []


def _turn_markers(wheelset_id: int, asof: pd.Timestamp) -> list[dict]:
    """Turn/replacement markers from the confirmed lifecycle turns table.

    Each marker carries the pre/post profile state per dim plus the diameter
    cut, so a renderer (ECharts or Matplotlib) never needs the raw tables.
    Only turns whose post_ts is <= asof are included (the chart is anchored).
    """
    try:
        turns = pd.read_parquet(TURNS)
    except Exception:
        return []
    t = turns[turns["wheelset_equipment_id"] == wheelset_id].sort_values("post_ts")
    if t.empty:
        return []
    out = []
    for no, (_, r) in enumerate(t.iterrows(), start=1):
        post = pd.Timestamp(r["post_ts"])
        if post > asof:
            continue
        pre = pd.Timestamp(r["pre_ts"]) if pd.notna(r.get("pre_ts")) else post
        out.append({
            "turn_no": no,
            "pre_ts": pre,
            "post_ts": post,
            "segment_index": _f(r.get("segment_index")),
            "days_between": _f(r.get("days_between")),
            "pre_wsmDia": _f(r.get("pre_wsmDia")),
            "post_wsmDia": _f(r.get("post_wsmDia")),
            "dia_cut": _f(r.get("cut_dia")),
            "pre_wsmFlange": _f(r.get("pre_wsmFlange")),
            "post_wsmFlange": _f(r.get("post_wsmFlange")),
            "pre_wsmRoot": _f(r.get("pre_wsmRoot")),
            "post_wsmRoot": _f(r.get("post_wsmRoot")),
            "pre_wsmThread": _f(r.get("pre_wsmThread")),
            "post_wsmThread": _f(r.get("post_wsmThread")),
        })
    return out


def trajectory(wheelset_id: int, asof: pd.Timestamp | None = None) -> dict:
    """Chart-data contract for the trajectory panel (trajectory_chart_v1).

    Built for a single anchor (default = latest measurement; `asof` re-anchors
    at a historical measurement). Wear dims are primary; wsmDia is derived and
    flagged when the forecast would increase it. All values are levels
    (predicted = current + delta); physics flags are reported, never clipped.
    """
    wes_all = load_wes()
    w = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id].sort_values(
        "measurement_timestamp").reset_index(drop=True)
    if w.empty:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "asof": None,
                "contract": "trajectory_chart_v1", "model": None, "dims": [],
                "feature_coverage": None,
                "delta_metrics": {}, "time_to_limit_summary": None, "note": None}

    anchor = asof if asof is not None else pd.Timestamp(w.iloc[-1]["measurement_timestamp"])
    t = pd.to_datetime(w["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    anchor_ns = np.datetime64(pd.Timestamp(anchor), "us")
    pos = np.where(t_arr == anchor_ns)[0]
    if len(pos) == 0:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None,
                "asof": pd.Timestamp(anchor),
                "contract": "trajectory_chart_v1", "model": None, "dims": [],
                "feature_coverage": None,
                "delta_metrics": {}, "time_to_limit_summary": None,
                "note": "as-of is not a measurement timestamp"}
    p = int(pos[0])

    fr = extract_features(wheelset_id, pd.Timestamp(anchor), w=w)
    svc = degradation_models()
    meta = degradation_meta()
    cov = feature_coverage(fr, svc["num_feats"]) if fr is not None else None
    deg = {}
    if fr is not None:
        X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
        for dim in DIMM:
            cur = fr.get(f"mean_{dim}")
            deg[dim] = {"current": cur, "delta": {}, "predicted": {}}
            for h in HORIZONS:
                delta = float(svc["models"][(dim, h)].predict(X)[0])
                predicted = cur + delta if np.isfinite(delta) and cur is not None and np.isfinite(cur) else None
                deg[dim]["delta"][h] = delta
                deg[dim]["predicted"][h] = predicted

    # observed history up to (and including) the anchor
    seg_id = w["seg_id"].to_numpy(dtype="int64") if "seg_id" in w else w.get("seg_id")
    dims = []
    for dim in DIMM:
        vals = w[f"mean_{dim}"].to_numpy(dtype=float)
        cur = deg[dim]["current"] if dim in deg else None
        obs = []
        for i in range(p + 1):
            v = vals[i]
            if np.isfinite(v):
                obs.append({
                    "ts": pd.Timestamp(t.iloc[i]),
                    "value": round(float(v), 4),
                    "segment_index": int(seg_id[i]) if seg_id is not None else None,
                    "turn_event": bool(w.iloc[i].get("turn_event", False)),
                    "replacement": bool(w.iloc[i].get("replacement", False)),
                })
        forecasts = []
        flags = set()
        pred_map, low_map, high_map = {}, {}, {}
        for h in HORIZONS:
            pred = deg[dim]["predicted"].get(h) if dim in deg else None
            width = _conformal_width_mm(dim, h)
            pred_map[h], low_map[h], high_map[h] = pred, (pred - width) if (pred is not None and width is not None) else None, (pred + width) if (pred is not None and width is not None) else None
            forecasts.append({
                "dim": dim, "horizon": h,
                "asof_ts": pd.Timestamp(anchor) + pd.Timedelta(days=h),
                "current": round(float(cur), 4) if cur is not None and np.isfinite(cur) else None,
                "delta": round(float(deg[dim]["delta"][h]), 4) if dim in deg else None,
                "predicted": round(float(pred), 4) if pred is not None else None,
                "low": round(float(low_map[h]), 4) if low_map[h] is not None else None,
                "high": round(float(high_map[h]), 4) if high_map[h] is not None else None,
                "model_version": meta.get("model_version"),
                "train_cutoff": meta.get("train_cutoff"),
                "feature_coverage": cov,
                "subgroup_flags": subgroup_flags(fr, dim, h) if fr is not None else [],
            })
            flags.update(_physics_flags(dim, cur, pred))
        time_to_limit = _time_to_limit(dim, cur, pred_map, low_map, high_map)

        # realised: future within-segment measurements inside each horizon
        realised = []
        for h in HORIZONS:
            hi = int(np.searchsorted(t_arr, anchor_ns + h * DAY, side="right"))
            b = int(np.searchsorted(seg_id, seg_id[p], side="right")) if seg_id is not None else 0
            last_same = min(hi, b) - 1
            if last_same > p:
                actual = vals[last_same]
                pred = deg[dim]["predicted"].get(h) if dim in deg else None
                if np.isfinite(actual):
                    realised.append({
                        "dim": dim, "horizon": h,
                        "ts": pd.Timestamp(t.iloc[last_same]),
                        "actual": round(float(actual), 4),
                        "residual": round(float(actual - pred), 4) if pred is not None else None,
                        "observed_in_horizon": True,
                    })

        dims.append({
            "dim": dim,
            "observed": obs,
            "forecasts": forecasts,
            "realised": realised,
            "flags": sorted(flags),
            "noise_floor_mm": _noise_floor_mm(dim),
            "time_to_limit": time_to_limit,
        })

    # model metadata from the degradation serving manifest + features.json
    meta = None
    try:
        meta = {
            "task": degradation_meta().get("task"),
            "target_mode": "delta",
            "train_cutoff": degradation_meta().get("train_cutoff"),
            "n_train": degradation_meta().get("n_train"),
            "model_version": degradation_meta().get("model_version"),
        }
    except Exception:
        pass

    # time-to-limit summary: only dims with an approved limit participate;
    # limiting dim = the one that reaches its limit soonest on the point path.
    ttl_rows = [d["time_to_limit"] for d in dims if d.get("time_to_limit")]
    limiting = None
    if ttl_rows:
        ranked = sorted(
            ttl_rows,
            key=lambda x: (x["days_to_limit_point"] is not None,
                           x["days_to_limit_point"] if x["days_to_limit_point"] is not None else 1e12))
        limiting = ranked[0]
    summary = {
        "status": limiting["status"] if limiting else "no_approved_limit",
        "limiting_dim": limiting["dim"] if limiting else None,
        "limit_mm": limiting["limit_mm"] if limiting else None,
        "current_mm": limiting["current_mm"] if limiting else None,
        "days_to_limit_point": limiting["days_to_limit_point"] if limiting else None,
        "days_to_limit_lo": limiting["days_to_limit_lo"] if limiting else None,
        "days_to_limit_hi": limiting["days_to_limit_hi"] if limiting else None,
        "note": ("Condemning limit 1016 mm (dia) is the only approved hard stop. "
                 "Flange/root/tread action limits are pending engineering "
                 "sign-off and are not reported."),
    }

    # loco number + identity for full context in the contract
    loco_number = None
    try:
        wes_row = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id]["LomNumber"].dropna()
        if len(wes_row):
            loco_number = str(wes_row.iloc[-1])
    except Exception:
        pass

    return {
        "wheelset_equipment_id": wheelset_id,
        "loco_number": loco_number,
        "anchor": pd.Timestamp(anchor),
        "asof": pd.Timestamp(anchor),
        "contract": "lifecycle_chart_v1",
        "units": {"length": "mm", "time": "days"},
        "model": meta,
        "feature_coverage": cov,
        "dims": dims,
        "turns": _turn_markers(wheelset_id, pd.Timestamp(anchor)),
        "delta_metrics": _delta_metrics_slim(),
        "time_to_limit_summary": summary,
        "note": ("Lifecycle chart contract (lifecycle_chart_v1): forecast = "
                 "anchor + delta; 80% split-conformal bands + noise floor from "
                 "the trajectory artefact; physics flags reported, never "
                 "clipped; turn markers carry pre/post profile state + dia "
                 "cut so renderers never read raw tables."),
    }


def loco_lookup(loco_number: str) -> pd.DataFrame:
    wes = load_wes()
    lom = str(loco_number).strip().lower()
    target = wes[wes["LomNumber"].astype(str).str.lower().eq(lom)]
    if target.empty:
        return pd.DataFrame()
    return target.drop_duplicates("wheelset_equipment_id")


def loco_summary(loco_number: str) -> dict:
    wes = load_wes()
    lom = str(loco_number).strip().lower()
    target = wes[wes["LomNumber"].astype(str).str.lower().eq(lom)]
    if target.empty:
        return {"loco_number": loco_number, "locomotive_id": None,
                "wheelsets": [], "n_wheelsets": 0}
    rows = []
    seg = load_segments()
    turns = pd.read_parquet(TURNS)
    turns = turns[turns["wheelset_equipment_id"].isin(target["wheelset_equipment_id"])]
    for (ws, grp) in target.sort_values("measurement_timestamp").groupby("wheelset_equipment_id"):
        last = grp.iloc[-1]
        rows.append({
            "wheelset_equipment_id": int(ws),
            "loco_number": loco_number,
            "locomotive_id": int(target.iloc[0]["locomotive_id"]),
            "latest_measurement": pd.Timestamp(last["measurement_timestamp"]).isoformat(),
            "latest_mean_wsmDia": _f(last["mean_wsmDia"]),
            "latest_mean_wsmFlange": _f(last["mean_wsmFlange"]),
            "latest_mean_wsmRoot": _f(last["mean_wsmRoot"]),
            "latest_mean_wsmThread": _f(last["mean_wsmThread"]),
            "days_since_turning": _f(last["days_since_turning"]),
            "distance_since_turning_km": _f(last["distance_since_turning_km"]),
            "n_turns": int((turns["wheelset_equipment_id"] == ws).sum()),
            "wheel_position_1_12": _f(last["wheel_position_1_12"]),
            "axle_position_1_6": _f(last["axle_position_1_6"]),
            "wheel_profile_2class": _f(last["wheel_profile_2class"]),
        })
    s = seg[seg["wheelset_equipment_id"].isin(target["wheelset_equipment_id"])]
    return {
        "loco_number": loco_number,
        "locomotive_id": int(target.iloc[0]["locomotive_id"]),
        "home_shed": str(target.iloc[-1]["home_shed"]) if pd.notna(target.iloc[-1]["home_shed"]) else None,
        "loco_type": str(target.iloc[0]["LocoType"]) if pd.notna(target.iloc[0]["LocoType"]) else None,
        "n_wheelsets": len(rows),
        "n_segments": int(s[["wheelset_equipment_id", "segment_index"]].drop_duplicates().shape[0]) if not s.empty else 0,
        "n_turns": int(turns.shape[0]),
        "wheelsets": rows,
    }


def loco_wheelset_table(loco_number: str) -> dict:
    """Enhanced loco wheelset table (P2.3): current state + forecasts + P(turn)
    + limiting dimension per wheelset.

    The snapshot (one row per wheelset, current state) carries the degradation
    forecast, P(turn) and limiting dimension; we merge it back onto the live
    wheelset list so the table shows both identity and model output.
    """
    base = loco_summary(loco_number)
    if not base["wheelsets"]:
        return base
    snap = _snapshot_df()
    snap_loco = None
    if snap is not None and "loco_number" in snap.columns:
        snap_loco = snap[snap["loco_number"].astype(str).eq(str(loco_number))]

    rows = []
    for w in base["wheelsets"]:
        ws = w["wheelset_equipment_id"]
        row = dict(w)
        if snap_loco is not None:
            m = snap_loco[snap_loco["wheelset_equipment_id"] == ws]
            if not m.empty:
                r = m.iloc[0]
                row["limiting_dim"] = r["limiting_dim"] if pd.notna(r.get("limiting_dim")) else None
                row["limiting_reason"] = str(r["limiting_reason"]) if pd.notna(r.get("limiting_reason")) else None
                row["days_to_condemning_dia"] = _f(r.get("days_to_condemning_dia"))
                for h in (30, 60, 90):
                    row[f"pturn_{h}d"] = _f(r.get(f"pturn_{h}d"))
                for dim in WEAR_DIMS:
                    row[f"fc_{dim}_90d"] = _f(r.get(f"fc_{dim}_90d_pred"))
        rows.append(row)

    return {
        "loco_number": base["loco_number"],
        "locomotive_id": base["locomotive_id"],
        "home_shed": base["home_shed"],
        "loco_type": base["loco_type"],
        "n_wheelsets": len(rows),
        "n_segments": base["n_segments"],
        "n_turns": base["n_turns"],
        "wheelsets": rows,
        "snapshot_sourced": snap_loco is not None,
    }


def wheelset_history(wheelset_id: int) -> dict:
    wes = load_wes()
    w = wes[wes["wheelset_equipment_id"] == wheelset_id].sort_values("measurement_timestamp")
    if w.empty:
        return {"wheelset_equipment_id": wheelset_id, "measurements": [], "turns": []}
    out_m = []
    for _, r in w.iterrows():
        out_m.append({
            "measurement_timestamp": pd.Timestamp(r["measurement_timestamp"]).isoformat(),
            "mean_wsmDia": _f(r["mean_wsmDia"]),
            "mean_wsmFlange": _f(r["mean_wsmFlange"]),
            "mean_wsmRoot": _f(r["mean_wsmRoot"]),
            "mean_wsmThread": _f(r["mean_wsmThread"]),
            "mean_wsmFlangeThickness": _f(r["mean_wsmFlangeThickness"]),
            "mean_wsmWheelGauge": _f(r["mean_wsmWheelGauge"]),
            "segment_index": _f(r["seg_id"]),
            "turn_event": bool(r["turn_event"]),
            "replacement": bool(r["replacement"]),
            "days_since_turning": _f(r["days_since_turning"]),
        })
    turns = pd.read_parquet(TURNS)
    t = turns[turns["wheelset_equipment_id"] == wheelset_id].sort_values("post_ts")
    out_t = []
    for _, r in t.iterrows():
        out_t.append({
            "wheelset_equipment_id": wheelset_id,
            "pre_ts": pd.Timestamp(r["pre_ts"]).isoformat(),
            "post_ts": pd.Timestamp(r["post_ts"]).isoformat(),
            "pre_wsmDia": _f(r.get("pre_wsmDia")),
            "post_wsmDia": _f(r.get("post_wsmDia")),
            "delta_wsmDia": round(_f(r.get("delta_wsmDia")), 4) if pd.notna(r.get("delta_wsmDia")) else None,
            "pre_wsmFlange": _f(r.get("pre_wsmFlange")),
            "post_wsmFlange": _f(r.get("post_wsmFlange")),
            "segment_index": _f(r.get("segment_index")),
            "delta_wsmFlangeThickness": round(_f(r.get("delta_wsmFlangeThickness")), 4)
            if pd.notna(r.get("delta_wsmFlangeThickness")) else None,
        })
    return {"wheelset_equipment_id": wheelset_id, "measurements": out_m, "turns": out_t}


def _f(v) -> float | None:
    try:
        x = float(v)
        return None if np.isnan(x) else round(x, 4)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# P1.1 fleet snapshot -> fleet overview / risk / search / shed endpoints
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _snapshot_df() -> pd.DataFrame | None:
    if not SNAPSHOT_PARQUET.exists():
        return None
    return pd.read_parquet(SNAPSHOT_PARQUET)


def fleet_overview() -> dict:
    """Fleet KPI summary + distributions from the P1.1 snapshot (single row/wheelset)."""
    df = _snapshot_df()
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    pturn_cols = [c for c in df.columns if c.startswith("pturn_")]
    wear_cols = [f"mean_{d}" for d in WEAR_DIMS]
    shed = (df.groupby("shed_any").size()
            .sort_values(ascending=False).head(10).rename("n_wheelsets").reset_index())
    return {
        "n_wheelsets": int(len(df)),
        "snapshot_built_at": _manifest_ts(),
        "model_version": _first_str(df, "model_version"),
        "train_cutoff": _first_str(df, "train_cutoff"),
        "staleness_days_median": _f(df["staleness_days"].median()) if "staleness_days" in df else None,
        "limiting_dim": {k: int(v) for k, v in df["limiting_dim"].value_counts(dropna=False).items()
                         if pd.notna(k)},
        "pturn_share_above_threshold_pct": {
            c.replace("pturn_", ""): round(float((df[c] >= 0.01).mean()) * 100, 2) for c in pturn_cols},
        "wear_distribution_mm": {
            c.replace("mean_", ""): {"q50": _f(df[c].quantile(0.5)), "q90": _f(df[c].quantile(0.9)),
                                     "q99": _f(df[c].quantile(0.99))} for c in wear_cols if c in df},
        "days_to_condemning_within_180d": int((df.get("days_to_condemning_dia", 0) <= 180).sum()),
        "feature_days_since_turning": {
            "q50": _f(df["days_since_turning"].quantile(0.5)) if "days_since_turning" in df else None,
            "q90": _f(df["days_since_turning"].quantile(0.9)) if "days_since_turning" in df else None},
        "top_sheds": shed.to_dict(orient="records"),
    }


def fleet_risk(shed: str | None = None, loco_type: str | None = None,
               limiting_dim: str | None = None, risk_level: str | None = None,
               sort_by: str = "pturn_90d", descending: bool = True,
               page: int = 1, page_size: int = 50) -> dict:
    """Paginated, filterable, rankable wheelset risk table (P2.2 fleet view)."""
    df = _snapshot_df()
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    if shed:
        df = df[df["shed_any"].astype(str).eq(shed)]
    if loco_type:
        df = df[df["loco_type"].astype(str).eq(loco_type)]
    if limiting_dim:
        df = df[df["limiting_dim"].astype(str).eq(limiting_dim)]
    if risk_level:
        # risk_level: "pturn" | "condemning" | "wear" - each level is its own cut
        if risk_level == "pturn":
            df = df[df["pturn_90d"] >= 0.01]
        elif risk_level == "condemning":
            df = df[df.get("days_to_condemning_dia", np.inf) <= 180]
        elif risk_level == "wear":
            df = df[df["limiting_dim"].isin(["wsmRoot", "wsmFlange", "wsmThread"])]

    if sort_by in df.columns and df[sort_by].notna().any():
        df = df.sort_values(sort_by, ascending=not descending, na_position="last")
    total = int(len(df))
    start = (page - 1) * page_size
    page_df = df.iloc[start:start + page_size]
    cols = ["wheelset_equipment_id", "loco_number", "shed_any", "loco_type",
            "limiting_dim", "limiting_reason", "days_to_condemning_dia",
            "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
            "feature_coverage", "staleness_days", "latest_measurement"]
    cols = [c for c in cols if c in page_df.columns]
    items = (page_df[cols].fillna(np.nan).replace({np.nan: None}).to_dict("records"))
    for item in items:
        lm = item.get("latest_measurement")
        if lm is not None:
            item["latest_measurement"] = str(lm) if isinstance(lm, (pd.Timestamp, str)) else lm
    pt_cols = [c for c in page_df.columns if c.startswith("pturn_")]
    for item, (_, r) in zip(items, page_df.iterrows()):
        for c in pt_cols:
            item[c] = _f(r[c])
    return {"total": total, "page": page, "page_size": page_size,
            "items": items, "columns": cols + pt_cols}


def fleet_search(q: str) -> dict:
    """Search loco number / shed / loco type from the snapshot."""
    df = _snapshot_df()
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    qn = str(q).strip().lower()
    if not qn:
        return {"query": q, "items": []}
    masks = []
    if "loco_number" in df.columns:
        masks.append(df["loco_number"].astype(str).str.lower().str.contains(qn, na=False))
    if "shed_any" in df.columns:
        masks.append(df["shed_any"].astype(str).str.lower().str.contains(qn, na=False))
    if "loco_type" in df.columns:
        masks.append(df["loco_type"].astype(str).str.lower().str.contains(qn, na=False))
    hit = masks[0] if len(masks) == 1 else (masks[0] | pd.Series(False, index=df.index))
    for m in masks[1:]:
        hit |= m
    sub = df.loc[hit]
    items = []
    if "loco_number" in sub.columns:
        for lnum, grp in sub.groupby("loco_number"):
            items.append({"loco_number": lnum,
                          "shed": str(grp["shed_any"].iloc[0]) if "shed_any" in grp else None,
                          "loco_type": str(grp["loco_type"].iloc[0]) if "loco_type" in grp else None,
                          "n_wheelsets": int(len(grp))})
    return {"query": q, "total": int(len(items)), "items": items}


def shed_overview(shed: str) -> dict:
    """Shed-level aggregation from the snapshot."""
    df = _snapshot_df()
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    if "shed_any" not in df.columns:
        return {"shed": shed, "n_wheelsets": 0, "error": "snapshot has no shed_any column"}
    sub = df[df["shed_any"].astype(str).eq(str(shed))]
    if sub.empty:
        locos = df[df["loco_number"].astype(str).eq(str(shed))]
        if locos.empty:
            return {"shed": shed, "n_wheelsets": 0}
        sub = locos
    return {
        "shed": shed,
        "n_wheelsets": int(len(sub)),
        "n_locos": int(sub["loco_number"].nunique()) if "loco_number" in sub else 0,
        "limiting_dim": {k: int(v) for k, v in sub["limiting_dim"].value_counts(dropna=False).items()
                         if pd.notna(k)},
        "pturn_90d_mean_pct": round(float(sub["pturn_90d"].mean()) * 100, 2) if "pturn_90d" in sub else None,
        "pturn_90d_p90_pct": round(float(sub["pturn_90d"].quantile(0.9)) * 100, 2) if "pturn_90d" in sub else None,
        "days_to_condemning_within_180d": int((sub.get("days_to_condemning_dia", 0) <= 180).sum()),
        "staleness_days_median": _f(sub["staleness_days"].median()) if "staleness_days" in sub else None,
    }


def _first_str(df: pd.DataFrame, col: str) -> str | None:
    if col not in df.columns:
        return None
    v = df[col].dropna()
    return str(v.iloc[0]) if len(v) else None


def _manifest_ts() -> str | None:
    try:
        return json.loads(SNAPSHOT_MANIFEST.read_text()).get("built_at_utc")
    except Exception:
        return None