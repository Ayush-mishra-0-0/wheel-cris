"""Layer 5 serving feature extractor.

Builds the exact feature vector the Layer-2 degradation models consume for an
arbitrary (wheelset, measurement) anchor, using point-in-time data only:

  - WES v1.0  (per-measurement wheel state + turning/RTIS/exposure ids + age)
  - exposure  (approved interval_distance_km / per-day km / distance-since-turn)
  - lifecycle_segments_shed (segment_index, n_prior_turns, shed attribution)

Replacement censoring replicates build_degradation_substrate.py (wsmProvDate
change OR wheel-age reset), so turn-only / partial histories like Loco 37597
are handled without the (unavailable) engineering_event_ledger.

Validated against the frozen v5 degradation substrate: all shared columns
match; `days_since_segment_start` is the one documented divergence (the
substrate sourced it from the ledger; it is ~75% NaN in training anyway and
the XGB models consume NaN natively).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
EXPOSURE = ROOT / "model_datasets" / "v2" / "exposure_features_v2.parquet"
SEG = ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet"

DAY = np.timedelta64(1, "D")
HORIZONS = (30, 90, 180)
SLOPE_DIMS = ("wsmFlange", "wsmThread")
RATE_DIMS = (("wsmRoot", (30, 90)), ("wsmDia", (30, 90)))

from models.phase5.build_lifecycle_segments import (  # noqa: E402
    SIDE_FIELDS, compute_boundaries, reset_aware_window_base, side_mean,
)


@lru_cache(maxsize=1)
def load_wes() -> pd.DataFrame:
    wes = pd.read_parquet(WES)
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    with np.errstate(invalid="ignore"):
        for f in SIDE_FIELDS:
            wes[f"mean_{f}"] = side_mean(wes, f)
    exp = pd.read_parquet(EXPOSURE, columns=[
        "operational_exposure_id", "interval_distance_km",
        "distance_per_day_km", "distance_since_turning_km"])
    wes = wes.merge(exp, on="operational_exposure_id", how="left")
    return _boundaries(wes)


@lru_cache(maxsize=1)
def load_segments() -> pd.DataFrame:
    return pd.read_parquet(SEG)


def _boundaries(wes: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(wes["measurement_timestamp"])
    wes["_ts"] = t.to_numpy(dtype="datetime64[us]")
    wes["turn_flag"] = wes["turning_record_at_measurement"].eq(1)
    return compute_boundaries(wes)


def extract_features(wheelset_id: int, anchor: pd.Timestamp,
                     w: pd.DataFrame | None = None) -> dict | None:
    """Feature row for one wheelset+measurement anchor (None if not in WES)."""
    seg = load_segments()
    if w is None:
        w = load_wes()[load_wes()["wheelset_equipment_id"] == wheelset_id].copy()
    if w.empty:
        return None
    w = w.sort_values("measurement_timestamp").reset_index(drop=True)
    t = pd.to_datetime(w["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    anchor_ns = np.datetime64(pd.Timestamp(anchor), "us")
    pos = np.where(t_arr == anchor_ns)[0]
    if len(pos) == 0:
        return None
    p = int(pos[0])
    r = w.iloc[p]
    seg_arr = w["seg_id"].to_numpy(dtype="int64")
    boundary = bool(r.get("turn_event", False)) or bool(r.get("replacement", False))

    out: dict = {
        "wheelset_equipment_id": int(wheelset_id),
        "measurement_record_id": int(r["measurement_record_id"]),
        "measurement_timestamp": pd.Timestamp(anchor),
        "LomNumber": str(r["LomNumber"]) if pd.notna(r["LomNumber"]) else None,
    }
    for f in SIDE_FIELDS:
        out[f"mean_{f}"] = _to_float(r[f"mean_{f}"])

    # flange/thread trailing per-day slopes (substrate SLOPE_DIMS loop).
    # Reset-aware: the trailing window is clamped to the anchor's segment start
    # so a turn/replacement inside the window (restore) can never corrupt the
    # rate; a fresh boundary anchor has no in-segment history -> NaN.
    for dim in SLOPE_DIMS:
        vv = w[f"mean_{dim}"].to_numpy(dtype=float)
        for Wd in HORIZONS:
            base = _segment_base(t_arr, seg_arr, p, Wd)
            span_use = (t_arr[p] - t_arr[base]) / DAY
            if base < p and np.isfinite(span_use) and span_use > 0 \
                    and np.isfinite(vv[p]) and np.isfinite(vv[base]):
                out[f"ph5_{dim}_rate_per_day_{Wd}d"] = _to_float((vv[p] - vv[base]) / span_use)
            else:
                out[f"ph5_{dim}_rate_per_day_{Wd}d"] = np.nan

    # root/dia trailing per-day rates at 30/90 (reset-aware, same window clamp)
    for dim, windows in RATE_DIMS:
        st = w[f"mean_{dim}"].to_numpy(dtype=float)
        for Wd in windows:
            base = _segment_base(t_arr, seg_arr, p, Wd)
            span = (t_arr[p] - t_arr[base]) / DAY
            if base < p and np.isfinite(st[p]) and np.isfinite(st[base]) and span > 1e-9:
                out[f"{dim}_rate_per_day_{Wd}d"] = _to_float((st[p] - st[base]) / span)
            else:
                out[f"{dim}_rate_per_day_{Wd}d"] = np.nan

    # km / inspection windows (v3e accum logic)
    fkm = w["interval_distance_km"].to_numpy(dtype=float)
    avail = (~np.isnan(fkm)).astype(float)
    km_cum = np.concatenate([[0.0], np.nan_to_num(fkm).cumsum()])
    av_cum = np.concatenate([[0.0], np.cumsum(avail)])
    repl = np.flatnonzero(w["replacement"].to_numpy())
    seg_start_ts = t_arr[repl[repl < p]].max() if np.any(repl < p) else t_arr[0]
    for Wd in HORIZONS:
        low = t_arr[p] - np.timedelta64(Wd, "D")
        eff = max(low, seg_start_ts)
        lo_idx = int(np.searchsorted(t_arr, eff, side="left"))
        has_prior = lo_idx < p
        if has_prior:
            out[f"km_last_{Wd}d"] = _to_float(km_cum[p] - km_cum[lo_idx])
            out[f"km_{Wd}d_available"] = bool((av_cum[p] - av_cum[lo_idx]) > 0)
            out[f"inspection_count_{Wd}d"] = float(p - lo_idx)
        else:
            out[f"km_last_{Wd}d"] = np.nan
            out[f"km_{Wd}d_available"] = False
            out[f"inspection_count_{Wd}d"] = 0.0

    out["days_since_turning"] = 0.0 if boundary else _to_float(r["days_since_turning"])
    out["wheel_age_days_proxy"] = _to_float(r["wheel_age_days_proxy"])
    out["rtis_reporting_coverage_pct"] = _to_float(r["rtis_reporting_coverage_pct"])
    out["distance_since_turning_km"] = _to_float(r["distance_since_turning_km"])
    out["distance_per_day_km"] = _to_float(r["distance_per_day_km"])
    if p > 0:
        out["days_since_last_inspection"] = float((t_arr[p] - t_arr[p - 1]) / DAY)
    else:
        out["days_since_last_inspection"] = np.nan
    out["days_since_segment_start"] = float((t_arr[p] - seg_start_ts) / DAY)
    out["LocoType"] = str(r["LocoType"]) if pd.notna(r["LocoType"]) else "NA"
    out["home_shed"] = str(r["home_shed"]) if pd.notna(r["home_shed"]) else "NA"
    out["defect_zone"] = str(r["defect_zone"]) if pd.notna(r["defect_zone"]) else "NA"
    out["axle_position_1_6"] = _to_float(r["axle_position_1_6"])
    out["wheel_position_1_12"] = _to_float(r["wheel_position_1_12"])
    out["wheel_profile_2class"] = _to_float(r["wheel_profile_2class"])
    out["segment_index"] = int(w.iloc[p]["seg_id"])

    s = seg[(seg["wheelset_equipment_id"] == wheelset_id) &
            (seg["segment_index"] == out["segment_index"])]
    if not s.empty:
        srow = s.iloc[0]
        out["n_prior_turns"] = int(srow["n_prior_turns"])
        out["shed_any"] = str(srow["shed_any"]) if pd.notna(srow["shed_any"]) else "NA"
    else:
        out["n_prior_turns"] = int(w.iloc[p]["seg_id"])
        out["shed_any"] = "NA"
    return out


def latest_anchor(wheelset_id: int) -> pd.Timestamp | None:
    wes_all = load_wes()
    w = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id]
    if w.empty:
        return None
    return w.sort_values("measurement_timestamp").iloc[-1]["measurement_timestamp"]


def _to_float(v) -> float:
    if v is None or pd.isna(v):
        return np.nan
    return float(v)


def _segment_base(t_arr: np.ndarray, seg_arr: np.ndarray, p: int, Wd: int) -> int:
    """Reset-aware trailing-window base index for one anchor.

    clamps the raw window base to the anchor's segment start so a
    turn/replacement restore inside the window never enters the rate span.
    """
    seg_start = int(np.searchsorted(seg_arr, seg_arr[p], side="left"))
    lo = int(np.searchsorted(t_arr, t_arr[p] - Wd * DAY, side="left"))
    base = max(lo, seg_start)
    if base >= p:
        base = seg_start if seg_start < p else p
    return base