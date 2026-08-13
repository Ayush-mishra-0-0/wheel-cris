"""Layer 5 - validation / backtest engine.

Two modes (both strict point-in-time):

A. Wheelset replay mode (on-demand):
   Freeze feature information at a chosen historical as-of date (anchor = a real
   measurement), run the degradation + P(turn) serving models, and compare the
   predictions to the ACTUAL future observations that did occur.

   Degradation (regression): target = last same-lifecycle-segment measurement
   value strictly inside (t, t+H] (identical to build_degradation_substrate.py).
   Implausibility flags: diameter forecast that INCREASES, or wear forecasts
   (root/flange/thread) that materially DECREASE ("wear improves") - reported
   with both model and actual baseline rates, never clipped.

   P(turn) (classification): actual = whether a CONFIRMED lifecycle turn's
   post_ts falls in (t, t+H]. Raw probabilities are exposed unrounded.

B. Fleet backtest (many historical anchors): reads the consolidated
   fleet_backtest.json produced by build_fleet_backtest.py (ROC-AUC, PR-AUC,
   Brier, ECE, capture@top5/10% for P(turn); MAE for root/flange/thread @
   30/90/180d; plus model-vs-actual implausibility rate diagnostics).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ._paths import ML_ROOT
from models.phase5.dashboard.backend.features import (
    extract_features, load_segments, load_wes,
)
from . import service

ROOT = ML_ROOT
TURNS = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
FLEET = ROOT / "models" / "experiments" / "v5" / "fleet_backtest.json"

DAY = np.timedelta64(1, "D")
HORIZONS = (30, 90, 180)
DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
WEAR_DIMS = ("wsmRoot", "wsmFlange", "wsmThread")
WEAR_BETTER_TOL = 0.05      # mm threshold below current to flag "wear improves"
DIA_INC_TOL = 0.001         # mm; predicted diameter above current


def _load_confirmed_turns() -> pd.DataFrame:
    t = pd.read_parquet(TURNS)
    t["post_ts"] = pd.to_datetime(t["post_ts"])
    consistent = (
        (t["pre_wsmDia"] > t["post_wsmDia"])
        & (t["pre_wsmFlange"] >= t["post_wsmFlange"])
        & (t["pre_wsmRoot"] >= t["post_wsmRoot"])
        & (t["pre_wsmThread"] >= t["post_wsmThread"]))
    return t[consistent].copy()


def _within_segment_actuals(ws_w: pd.DataFrame, anchor_pos: int):
    """Mirror of build_degradation_substrate target computation for one wheelset.
    Returns {dim: {H: actual_or_nan}} and target_ts."""
    w = ws_w.sort_values("measurement_timestamp").reset_index(drop=True)
    tg = pd.to_datetime(w["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    sg = w["seg_id"].to_numpy(dtype="int64")
    vs = {dim: w[f"mean_{dim}"].to_numpy(dtype=float) for dim in DIMM}
    p = anchor_pos
    tgt = {}
    tts = {}
    for H in HORIZONS:
        hi = int(np.searchsorted(tg, tg[p] + np.timedelta64(H, "D"), side="right"))
        b = int(np.searchsorted(sg, sg[p], side="right"))
        last_same = min(hi, b) - 1
        if last_same > p:
            tgt[H] = {dim: vs[dim][last_same] for dim in DIMM}
            tts[H] = tg[last_same]
        else:
            tgt[H] = None
            tts[H] = None
    return tgt, tts


def _anchor_position(w: pd.DataFrame, anchor: pd.Timestamp) -> int | None:
    w = w.sort_values("measurement_timestamp").reset_index(drop=True)
    t_arr = pd.to_datetime(w["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    anchor_ns = np.datetime64(pd.Timestamp(anchor), "us")
    pos = np.where(t_arr == anchor_ns)[0]
    return int(pos[0]) if len(pos) else None


def wheelset_replay(wheelset_id: int, as_of: pd.Timestamp):
    """Freeze features at `as_of`, predict, compare to actual future obs."""
    wes_all = load_wes()
    w = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id].sort_values(
        "measurement_timestamp").reset_index(drop=True)
    if w.empty:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "error": "no data"}
    p = _anchor_position(w, as_of)
    if p is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": str(as_of),
                "error": "as-of date is not a measurement for this wheelset"}
    anchor_ts = pd.to_datetime(w.iloc[p]["measurement_timestamp"])

    fr = extract_features(wheelset_id, anchor_ts, w=w)
    if fr is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": str(anchor_ts),
                "error": "feature extraction failed for anchor"}

    # ---- actual future observations ----
    tgt, tts = _within_segment_actuals(w, p)

    # ---- actual P(turn) outcome ----
    turns = _load_confirmed_turns()
    tr = turns[turns["wheelset_equipment_id"] == wheelset_id]["post_ts"].to_numpy(
        dtype="datetime64[us]")
    t_arr = anchor_ts.to_numpy() if hasattr(anchor_ts, "to_numpy") else np.datetime64(anchor_ts, "us")
    pt_horizons = tuple(service.pturn_models()["models"].keys())
    turn_outcome = {}
    for H in pt_horizons:
        hi = t_arr + np.timedelta64(H, "D")
        n_ev = int(np.searchsorted(tr, hi, side="right") -
                   np.searchsorted(tr, t_arr, side="right"))
        turn_outcome[H] = {"actual_turned": bool(n_ev > 0), "n_events": int(n_ev)}

    # ---- model predictions ----
    deg_svc = service.degradation_models()
    Xdeg = service._feature_vector(fr, deg_svc["num_feats"], deg_svc["cat_feats"], deg_svc["enc"])
    forecasts = []
    for dim in DIMM:
        for h in HORIZONS:
            pred = float(deg_svc["models"][(dim, h)].predict(Xdeg)[0])
            actual = tgt[h][dim] if tgt[h] else None
            current = fr.get(f"mean_{dim}")
            act_ts = tts[h]
            flag = None
            if np.isfinite(pred) and current is not None and np.isfinite(current):
                if dim == "wsmDia" and pred > current + DIA_INC_TOL:
                    flag = "increasing_diameter"
                elif dim in WEAR_DIMS and pred < current - WEAR_BETTER_TOL:
                    flag = "wear_better_than_current"
            forecasts.append({
                "dim": dim, "horizon": h,
                "current": round(current, 4) if current is not None and np.isfinite(current) else None,
                "predicted": round(pred, 4),
                "actual": round(actual, 4) if actual is not None and np.isfinite(actual) else None,
                "actual_ts": str(pd.Timestamp(act_ts).date()) if act_ts is not None else None,
                "observed_in_horizon": actual is not None and np.isfinite(actual),
                "implausibility_flag": flag,
                "mae": round(abs(pred - actual), 4) if actual is not None and np.isfinite(actual) else None,
            })

    # ---- P(turn) predictions (raw probabilities, unrounded) ----
    pt_svc = service.pturn_models()
    Xpt = service._feature_vector(fr, pt_svc["num_feats"], pt_svc["cat_feats"], pt_svc["enc"])
    pturn = []
    for h in pt_svc["models"]:
        m = pt_svc["models"][h]
        p_prob = float(m.predict_proba(Xpt)[0, 1])
        out = turn_outcome.get(h, {})
        pturn.append({
            "horizon": h,
            "probability_raw": p_prob,
            "probability_pct": round(p_prob * 100, 2),
            "turn_rate_train": pt_svc["turn_rate_train"].get(h),
            "actual_turned": out.get("actual_turned"),
            "actual_n_events": out.get("n_events"),
        })

    return {
        "wheelset_equipment_id": wheelset_id,
        "anchor": str(anchor_ts),
        "loco_number": str(w.iloc[p]["LomNumber"]) if pd.notna(w.iloc[p]["LomNumber"]) else None,
        "degradation": forecasts,
        "turn_probability": pturn,
        "note": ("Strict point-in-time: features use only information at "
                 "anchor; predictions compared against actual future within-segment "
                 "observations / confirmed turns. Implausibility flags are reported, "
                 "never clipped."),
    }


def fleet_metrics() -> dict:
    if not FLEET.exists():
        return {"error": f"fleet_backtest.json not built: {FLEET.relative_to(ROOT)}"}
    return json.loads(FLEET.read_text())
