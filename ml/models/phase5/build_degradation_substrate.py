"""Phase 5 Layer 2 - degradation-benchmark substrate builder.

Anchors are the frozen v3f within-lifecycle rows (239,684, temporal split
preserved) carrying the Phase 4 point-in-time feature machinery (rates, km,
RTIS coverage, wear-rate slopes). Each anchor is an inspection at time t.

On top of the frozen features, this layer adds:

  1. Phase-5 lifecycle attributes (from the v5 segment reconstructor):
     segment_index, n_prior_turns, shed attribution, open/close flags.
  2. Post-turn eligibility (contract v1.1/v1.2 section 4): drop an anchor when
     a turn/replacement event occurs within k days AFTER it (default k=3d) -
     those rows are the wheel parked for machining, not an operating state.
     The post-turn (fresh) measurement itself remains a valid anchor.
  3. Within-segment horizon targets (contract v1.2 section 4): target dim at
     horizon H = last same-lifecycle-segment measurement value strictly inside
     (t, t+H]. No turn/replacement crossing by construction (segments split at
     boundaries). NaN (excluded) when no such measurement exists.
  4. target_obs_ts per (dim,H): the measurement time of the target, so rolling
     benchmarks can enforce point-in-time label determinability (label known
     only if target_obs_ts <= cutoff T).

Consumes: v3/wheel_engineering_state_v1.0.parquet (immutable),
         v3f/change_space_benchmark.parquet (frozen features + split),
         v5/lifecycle_segments_shed.parquet (segment attrs + shed).
Outputs:  model_datasets/v5/degradation_benchmark.parquet (+ SHA256 manifest).
"""
from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from models.phase5.build_lifecycle_segments import (  # noqa: E402
    GATES, SIDE_FIELDS, compute_boundaries, reset_aware_window_base, side_mean,
)

WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
SEG = ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet"
OUT = ROOT / "model_datasets" / "v5"

HORIZONS = (30, 90, 180)
TARGET_DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
K_DAYS = 3
RATE_DIMS = (("wsmRoot", (30, 90)), ("wsmDia", (30, 90)))

# v3f point-in-time feature columns retained (same list as v4 build_risk_benchmark)
FEATURE_COLUMNS = [
    "wsmDia1", "wsmDia2", "wsmFlangeThickness1", "wsmFlangeThickness2",
    "wsmRoot1", "wsmRoot2", "wsmWheelGauge1", "wsmWheelGauge2",
    "wsmDia1_quality", "wsmDia2_quality", "wsmFlangeThickness1_quality",
    "wsmFlangeThickness2_quality", "wsmRoot1_quality", "wsmRoot2_quality",
    "wsmWheelGauge1_quality", "wsmWheelGauge2_quality",
    "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
    "days_since_turning", "wheel_age_days_proxy",
    "days_since_last_inspection", "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d", "inspection_count_180d",
    "km_last_30d", "km_30d_available", "km_last_90d", "km_90d_available",
    "km_last_180d", "km_180d_available",
    "wsmRoot_change_last_30d", "wsmRoot_rate_per_day_30d",
    "wsmRoot_change_last_90d", "wsmRoot_rate_per_day_90d",
    "wsmRoot_change_last_180d", "wsmRoot_rate_per_day_180d",
    "wsmRoot_rate_per_1000km_30d", "wsmRoot_rate_per_1000km_90d",
    "wsmRoot_rate_per_1000km_180d",
    "wsmDia_change_last_30d", "wsmDia_rate_per_day_30d",
    "wsmDia_change_last_90d", "wsmDia_rate_per_day_90d",
    "wsmDia_change_last_180d", "wsmDia_rate_per_day_180d",
    "wsmDia_rate_per_1000km_30d", "wsmDia_rate_per_1000km_90d",
    "wsmDia_rate_per_1000km_180d",
    "wsmFlangeThickness_change_last_30d",
    "wsmFlangeThickness_rate_per_day_30d",
    "wsmFlangeThickness_change_last_90d",
    "wsmFlangeThickness_rate_per_day_90d",
    "distance_since_turning_km", "distance_per_day_km",
    "rtis_distance_coverage_pct_in_interval", "distance_available",
]

CATEGORICAL_COLUMNS = [
    "LocoType", "wheel_profile_2class", "home_shed", "defect_zone",
    "defect_division", "wheel_position_1_12", "axle_position_1_6",
]

META = [
    "measurement_record_id", "wheelset_equipment_id", "locomotive_id",
    "measurement_timestamp", "split",
]


def main() -> None:
    wes = pd.read_parquet(WES)
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)

    # ---- phase-5 gating + side means ----
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for f in SIDE_FIELDS:
            wes[f"mean_{f}"] = side_mean(wes, f)

    t = pd.to_datetime(wes["measurement_timestamp"])
    wes["_ts"] = t.to_numpy(dtype="datetime64[us]")
    wes["turn_flag"] = wes["turning_record_at_measurement"].eq(1)

    # ---- turn-event / replacement / segment id (identical logic to segments builder) ----
    wes = compute_boundaries(wes)

    # ---- anchors: frozen v3f within-lifecycle rows (join 100% coverage, no dupes) ----
    v3f = pd.read_parquet(V3F)
    keep_features = [c for c in FEATURE_COLUMNS + CATEGORICAL_COLUMNS if c in v3f.columns]
    v3f_sel = [c for c in META + keep_features
               if c in v3f.columns and c not in ("wheelset_equipment_id", "locomotive_id")]
    wes_sub = wes[["measurement_record_id", "wheelset_equipment_id", "locomotive_id",
                   "_ts", "seg_id", "turn_event", "replacement"] + [f"mean_{f}" for f in SIDE_FIELDS]]
    anc = v3f[v3f_sel].merge(wes_sub, on="measurement_record_id", how="left",
                             validate="one_to_one")

    # ---- segment-level attributes (v5) ----
    seg = pd.read_parquet(SEG)
    seg_map = seg[["wheelset_equipment_id", "segment_index", "n_prior_turns",
                   "opens_at_turn", "opens_at_replacement", "closes_at_turn",
                   "shed_any", "shed_slam", "shed_fois", "station_fois"]].drop_duplicates(
        ["wheelset_equipment_id", "segment_index"])
    anc = anc.merge(seg_map, left_on=["wheelset_equipment_id", "seg_id"],
                    right_on=["wheelset_equipment_id", "segment_index"], how="left",
                    validate="many_to_one")

    # ---- per-wheelset sorted arrays ----
    wes["_pos"] = np.arange(len(wes), dtype=np.int64)
    pos_map = dict(zip(wes["measurement_record_id"], wes["_pos"]))
    eq_arr = wes["wheelset_equipment_id"].to_numpy(dtype="int64")
    t_arr = wes["_ts"].to_numpy()
    seg_arr = wes["seg_id"].to_numpy(dtype="int64")
    val = {f: wes[f"mean_{f}"].to_numpy(dtype=float) for f in SIDE_FIELDS}
    bounds = np.flatnonzero(np.r_[True, eq_arr[:-1] != eq_arr[1:], True])
    gs, ge = bounds[:-1], bounds[1:]
    grp_eq = eq_arr[gs]
    eq_lookup = {int(e): (s, e_) for e, s, e_ in zip(grp_eq, gs, ge)}

    a_eq = anc["wheelset_equipment_id"].to_numpy(dtype="int64")
    a_idx = np.arange(len(anc), dtype=np.int64)

    # absolute stream position of each anchor (1:1 join; present by construction)
    pos = anc["measurement_record_id"].map(pos_map).to_numpy(dtype="int64")

    # ---- per-anchor: transient exclusion + targets ----
    n = len(anc)
    transient = np.zeros(n, dtype=bool)
    tgt_ts = {H: np.full(n, np.datetime64("NaT", "us"), dtype="datetime64[us]") for H in HORIZONS}
    tgt = {dim: {H: np.full(n, np.nan) for H in HORIZONS} for dim in TARGET_DIMS}
    elig = {dim: {H: np.zeros(n, dtype=bool) for H in HORIZONS} for dim in TARGET_DIMS}
    SLOPE_DIMS = ("wsmFlange", "wsmThread")
    chg = {}
    rt = {}
    for dim in SLOPE_DIMS:
        for W in HORIZONS:
            chg[(dim, W)] = np.full(n, np.nan)
            rt[(dim, W)] = np.full(n, np.nan)
    rtr = {dim: {W: np.full(n, np.nan) for W in wins} for dim, wins in RATE_DIMS}
    DAY = np.timedelta64(1, "D")

    for e in np.unique(a_eq):
        s, en = eq_lookup[int(e)]
        idx = a_idx[a_eq == e]
        if len(idx) == 0:
            continue
        tg = t_arr[s:en]
        sg = seg_arr[s:en]
        v = {dim: val[dim][s:en] for dim in TARGET_DIMS}
        p = pos[idx] - s
        for H in HORIZONS:
            step = np.timedelta64(H, "D")
            hi = np.searchsorted(tg, tg[p] + step, side="right")
            b = np.searchsorted(sg, sg[p], side="right")          # first row seg != anchor
            last_same = np.minimum(hi, b) - 1
            ok = last_same > p
            for dim in TARGET_DIMS:
                tgt[dim][H][idx[ok]] = v[dim][last_same[ok]]
                elig[dim][H][idx[ok]] = True
            tgt_ts[H][idx[ok]] = tg[last_same[ok]]
        # transient: next event within K_DAYS after anchor
        nxt = np.searchsorted(tg, tg[p] + np.timedelta64(K_DAYS, "D"), side="right")
        has_event = (b < en - s) & (b < nxt)
        transient[idx] = has_event
        # point-in-time trailing-window flange/thread wear slopes (reset-aware:
        # clamp window to segment start so turn/replacement restores never
        # corrupt the rate; mirror of features.py _segment_base)
        for dim in SLOPE_DIMS:
            vv = v[dim]
            for W in HORIZONS:
                lo = np.searchsorted(tg, tg[p] - W * DAY, side="left")
                seg_start = np.searchsorted(sg, sg[p], side="left")
                base = np.maximum(lo, seg_start)
                base = np.where(base >= p, np.where(seg_start < p, seg_start, p), base)
                span_days = (tg[p] - tg[base]) / DAY
                ok = (base < p) & (p > 0)
                chg_vec = np.full(len(p), np.nan)
                chg_vec[ok] = vv[p[ok]] - vv[base[ok]]
                span = np.where(ok, span_days, np.nan)
                chg[(dim, W)][idx] = chg_vec
                rt[(dim, W)][idx] = np.where(np.isfinite(span) & (span > 0),
                                             chg_vec / span, np.nan)
        # root/dia trailing per-day rates (same reset-aware window; overrides
        # the V3F-frozen values so train/serve stay in distribution)
        for dim, wins in RATE_DIMS:
            vv = v[dim]
            for W in wins:
                lo = np.searchsorted(tg, tg[p] - W * DAY, side="left")
                seg_start = np.searchsorted(sg, sg[p], side="left")
                base = np.maximum(lo, seg_start)
                base = np.where(base >= p, np.where(seg_start < p, seg_start, p), base)
                span = (tg[p] - tg[base]) / DAY
                ok = (base < p) & (p > 0)
                rate = np.full(len(p), np.nan)
                rate[ok] = np.where(span[ok] > 1e-9,
                                    (vv[p[ok]] - vv[base[ok]]) / np.maximum(span[ok], 1e-9), np.nan)
                rtr[dim][W][idx] = rate

    for dim in TARGET_DIMS:
        for H in HORIZONS:
            anc[f"tgt_{dim}_{H}d"] = tgt[dim][H]
            anc[f"eligible_{dim}_{H}d"] = elig[dim][H]
    for H in HORIZONS:
        anc[f"tgt_obs_ts_{H}d"] = tgt_ts[H]
    for dim in SLOPE_DIMS:
        for W in HORIZONS:
            anc[f"ph5_{dim}_change_last_{W}d"] = chg[(dim, W)]
            anc[f"ph5_{dim}_rate_per_day_{W}d"] = rt[(dim, W)]
    # root/dia rates: overwrite the V3F-frozen FEATURE_COLUMNS values with the
    # reset-aware recomputation (same window clamp as features.py RATE_DIMS).
    for dim, wins in RATE_DIMS:
        for W in wins:
            anc[f"{dim}_rate_per_day_{W}d"] = rtr[dim][W]
    # post-turn age fill: a boundary row (turn/replacement) is 0 days since
    # turning in reality; the V3F-frozen column is NaN there. Mirror features.py.
    if "turn_event" in anc and "replacement" in anc:
        boundary = anc["turn_event"].fillna(False) | anc["replacement"].fillna(False)
        anc.loc[boundary, "days_since_turning"] = 0.0

    # eligibility = not transient AND (all-dim targets as applicable); keep rows
    # with at least one eligible horizon for a usable regression target per dim.
    elig_cols = [f"eligible_{dim}_{H}d" for dim in TARGET_DIMS for H in HORIZONS]
    anc["any_eligible"] = anc[elig_cols].any(axis=1)
    anc["transient_excluded"] = transient

    # ---- output ----
    drop_me = [c for c in ["_ts", "seg_id"] if c in anc.columns]
    out = anc.drop(columns=drop_me)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "degradation_benchmark.parquet"
    out.to_parquet(path, index=False)

    summary = {
        "task": "phase 5 layer 2 degradation-benchmark substrate",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "anchor": "v3f within-lifecycle rows (frozen split)",
        "source_wes": str(WES.relative_to(ROOT)),
        "source_v3f": str(V3F.relative_to(ROOT)),
        "source_segments": str(SEG.relative_to(ROOT)),
        "output": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": int(len(out)),
        "rows_train": int(out["split"].eq("train").sum()),
        "rows_test": int(out["split"].eq("test").sum()),
        "transient_excluded_3d": int(transient.sum()),
        "transient_pct": round(float(transient.mean() * 100), 2),
        "shed_coverage_pct": round(float(out["shed_any"].notna().mean() * 100), 2),
        "profile_class_coverage_pct": round(float(out["wheel_profile_2class"].notna().mean() * 100), 2),
        "horizons": list(HORIZONS),
        "target_dims": list(TARGET_DIMS),
        "per_dim_horizon": {},
    }
    for dim in TARGET_DIMS:
        for H in HORIZONS:
            el = out[f"eligible_{dim}_{H}d"].to_numpy()
            tv = out[f"tgt_{dim}_{H}d"].to_numpy()
            summary["per_dim_horizon"][f"{dim}_{H}d"] = {
                "eligible": int(el.sum()),
                "eligible_test": int((el & out["split"].eq("test").to_numpy()).sum()),
                "target_median": round(float(np.nanmedian(tv[el])), 3) if el.sum() else None,
            }
    (OUT / "degradation_benchmark_manifest.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
