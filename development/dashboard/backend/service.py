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

HORIZONS = (30, 90, 180)
DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")


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
        for h in HORIZONS:
            m = svc["models"][(dim, h)]
            pred = float(m.predict(X)[0])
            fc.append({"horizon": h, "dim": dim, "value": round(pred, 4)})
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