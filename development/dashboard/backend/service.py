"""Layer 5 dashboard - service layer (models + feature extraction).
"""
from __future__ import annotations

import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from ._paths import ML_ROOT
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
            flags = _physics_flags(dim, current, value)
            fc.append({"horizon": h, "dim": dim, "value": value,
                       "delta": round(delta, 4) if np.isfinite(delta) else None,
                       "current": round(float(current), 4)
                       if current is not None and np.isfinite(current) else None,
                       "implausibility_flag": flags[0] if flags else None,
                       "subgroup_flags": subgroup_flags(fr, dim, h)})
    return {"wheelset_equipment_id": wheelset_id, "anchor": anchor, "forecasts": fc}


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
                "delta_metrics": {}, "time_to_limit_summary": None,
                "note": "as-of is not a measurement timestamp"}
    p = int(pos[0])

    fr = extract_features(wheelset_id, pd.Timestamp(anchor), w=w)
    svc = degradation_models()
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
        feats = json.loads((DEG_DIR / "features.json").read_text())
        mf = json.loads((DEG_DIR / "manifest.json").read_text())
        meta = {
            "task": mf.get("task"),
            "target_mode": "delta",
            "train_cutoff": feats.get("train_cutoff"),
            "n_train": feats.get("n_train_rows"),
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

    return {
        "wheelset_equipment_id": wheelset_id,
        "anchor": pd.Timestamp(anchor),
        "asof": pd.Timestamp(anchor),
        "contract": "trajectory_chart_v1",
        "model": meta,
        "dims": dims,
        "delta_metrics": _delta_metrics_slim(),
        "time_to_limit_summary": summary,
        "note": ("Trajectory chart contract: forecast = anchor + delta; "
                 "80% split-conformal bands from the trajectory artefact; "
                 "physics flags reported, never clipped."),
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