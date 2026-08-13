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
            fc.append({"horizon": h, "dim": dim, "value": value,
                       "delta": round(delta, 4) if np.isfinite(delta) else None,
                       "current": round(float(current), 4)
                       if current is not None and np.isfinite(current) else None})
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
                "delta_metrics": {}, "note": None}

    anchor = asof if asof is not None else pd.Timestamp(w.iloc[-1]["measurement_timestamp"])
    t = pd.to_datetime(w["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    anchor_ns = np.datetime64(pd.Timestamp(anchor), "us")
    pos = np.where(t_arr == anchor_ns)[0]
    if len(pos) == 0:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None,
                "asof": pd.Timestamp(anchor),
                "contract": "trajectory_chart_v1", "model": None, "dims": [],
                "delta_metrics": {}, "note": "as-of is not a measurement timestamp"}
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
        for h in HORIZONS:
            pred = deg[dim]["predicted"].get(h) if dim in deg else None
            width = _conformal_width_mm(dim, h)
            forecasts.append({
                "dim": dim, "horizon": h,
                "asof_ts": pd.Timestamp(anchor) + pd.Timedelta(days=h),
                "current": round(float(cur), 4) if cur is not None and np.isfinite(cur) else None,
                "delta": round(float(deg[dim]["delta"][h]), 4) if dim in deg else None,
                "predicted": round(float(pred), 4) if pred is not None else None,
                "low": round(float(pred - width), 4) if pred is not None and width is not None else None,
                "high": round(float(pred + width), 4) if pred is not None and width is not None else None,
            })
            flags.update(_physics_flags(dim, cur, pred))

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

    return {
        "wheelset_equipment_id": wheelset_id,
        "anchor": pd.Timestamp(anchor),
        "asof": pd.Timestamp(anchor),
        "contract": "trajectory_chart_v1",
        "model": meta,
        "dims": dims,
        "delta_metrics": _delta_metrics_slim(),
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