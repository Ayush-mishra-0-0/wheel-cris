"""Phase 4 - build risk-benchmark dataset (v4).

Anchors on the frozen v3f within-lifecycle rows (all 239,684 rows, frozen
train/test split preserved, row order preserved). For each anchor row (an
inspection at time t) and each horizon H in {30, 90, 180}, labels:

    target A (root constraint): 1 if any future WES root measurement
        strictly inside (t, t+H] exceeds 3 mm (owner-confirmed condemning).
    target B (turning): 1 if a turning event day falls strictly inside
        (t, t+H] (equipment-day dedup per maintenance event spec).

Eligibility (per Risk Event Contract v1.0 section 4):
    eligible = (observation_end - t) >= H  OR  event within (t, t+H]
    label    = 1 if event within window
               0 if eligible and no event
               NaN (excluded / unknown follow-up) otherwise

Point-in-time: only state/context observable at t is kept as features.
Leakage rules (contract section 6): no next_* / delta_* / target_* / dX_* /
replacement_before_* / horizon_window / horizon_days / interval_days of the
FORWARD interval. Only within-lifecycle historical features are retained.

The turning signal comes from WES (v3f's own turning_record_at_measurement is
all-zero) joined via measurement_record_id; WES is the single look-ahead source
for both root and turning, keyed by wheelset_equipment_id.

Output:
    model_datasets/v4/risk_benchmark.parquet   (+ SHA256 manifest)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "model_datasets" / "v4"
HORIZONS = (30, 90, 180)
LIMIT_ROOT = 3.0

# Features observable at measurement time (point-in-time, no forward facts).
# Excludes the v3f forward-machinery columns (next_*, delta_*, target_*, dX_*,
# crosses_*, replacement_before_*, horizon_*, interval_days of the forward pair,
# prev/next record ids and times).
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
    "wsmDia_change_last_30d", "wsmDia_rate_per_day_30d",
    "wsmDia_change_last_90d", "wsmDia_rate_per_day_90d",
    "wsmFlangeThickness_change_last_30d",
    "wsmFlangeThickness_rate_per_day_30d",
    "wsmFlangeThickness_change_last_90d",
    "wsmFlangeThickness_rate_per_day_90d",
]
CATEGORICAL_COLUMNS = ["LocoType", "wheel_profile_2class", "home_shed",
                       "defect_zone", "defect_division",
                       "wheel_position_1_12", "axle_position_1_6",
                       "lifecycle_segment_id"]
KEEP_META = ["measurement_record_id", "wheelset_equipment_id",
             "measurement_timestamp", "split", "within_lifecycle"]


def state_mean(df):
    cols = ["wsmDia1", "wsmDia2", "wsmRoot1", "wsmRoot2",
            "wsmFlangeThickness1", "wsmFlangeThickness2", "wsmWheelGauge1", "wsmWheelGauge2"]
    out = {}
    for d in ["wsmDia", "wsmRoot", "wsmFlangeThickness", "wsmWheelGauge"]:
        a = df[f"{d}1"].to_numpy(dtype=float); b = df[f"{d}2"].to_numpy(dtype=float)
        q1 = df[f"{d}1_quality"].eq("OBSERVED_VALID").to_numpy()
        q2 = df[f"{d}2_quality"].eq("OBSERVED_VALID").to_numpy()
        out[f"{d}_mean"] = np.where(q1 & q2, (a + b) / 2.0,
                                    np.where(q1, a, np.where(q2, b, np.nan)))
    return out


def main() -> None:
    v3f = pd.read_parquet(V3F)
    wes = pd.read_parquet(WES, columns=[
        "wheelset_equipment_id", "measurement_timestamp",
        "turning_record_at_measurement",
        "wsmRoot1", "wsmRoot2", "wsmRoot1_quality", "wsmRoot2_quality"])

    # ---- point-in-time look-ahead source: per-equipment sorted future states ----
    r1 = wes["wsmRoot1"].to_numpy(dtype=float); r2 = wes["wsmRoot2"].to_numpy(dtype=float)
    q1 = wes["wsmRoot1_quality"].eq("OBSERVED_VALID").to_numpy()
    q2 = wes["wsmRoot2_quality"].eq("OBSERVED_VALID").to_numpy()
    wes["_root"] = np.where(q1 & q2, (r1 + r2) / 2.0,
                            np.where(q1, r1, np.where(q2, r2, np.nan)))
    wes["_turn"] = wes["turning_record_at_measurement"].eq(1).to_numpy()
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    wes["_t"] = pd.to_datetime(wes["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    wes["_eq"] = wes["wheelset_equipment_id"].astype("int64").to_numpy()
    obs_end = wes.groupby("_eq")["_t"].max()

    # per-equipment sorted arrays for searchsorted
    eq_keys = wes["_eq"].to_numpy()
    bounds = np.flatnonzero(np.r_[True, eq_keys[:-1] != eq_keys[1:], True])
    group_start = bounds[:-1]
    group_end = bounds[1:]
    group_eq = eq_keys[group_start]
    eq_lookup = {int(e): (s, e_) for e, s, e_ in zip(group_eq, group_start, group_end)}
    t_all = wes["_t"].to_numpy()
    root_all = wes["_root"].to_numpy()
    turn_all = wes["_turn"].to_numpy()

    df = v3f.copy()
    a_eq = df["wheelset_equipment_id"].astype("int64").to_numpy()
    a_t = pd.to_datetime(df["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    a_obs_end = np.array([obs_end.get(int(e), np.datetime64("NaT")) for e in a_eq],
                         dtype="datetime64[us]")

    for H in HORIZONS:
        step = np.timedelta64(H, "D")
        event_root = np.zeros(len(df), dtype=bool)
        event_turn = np.zeros(len(df), dtype=bool)
        for i in range(len(df)):
            e = int(a_eq[i])
            spec = eq_lookup.get(e)
            if spec is None:
                continue
            s, en = spec
            lo = np.searchsorted(t_all[s:en], a_t[i], side="right") + s
            hi = np.searchsorted(t_all[s:en], a_t[i] + step, side="right") + s
            if lo < hi:
                event_root[i] = bool(np.nanmax(root_all[lo:hi]) > LIMIT_ROOT) \
                    if np.isfinite(root_all[lo:hi]).any() else False
                event_turn[i] = bool(turn_all[lo:hi].any())
        full_window = (a_obs_end - a_t) >= step
        eligible = event_root | event_turn | full_window
        label_a = event_root.astype(float); label_a[~eligible] = np.nan
        label_b = event_turn.astype(float); label_b[~eligible] = np.nan
        df[f"root_within_{H}d"] = label_a
        df[f"turn_within_{H}d"] = label_b
        df[f"eligible_{H}d"] = eligible

    # ---- feature columns (point-in-time only) + meta ----
    keep = KEEP_META + FEATURE_COLUMNS + CATEGORICAL_COLUMNS
    for c in KEEP_META:
        if c not in df.columns:
            df[c] = np.nan
    for c in FEATURE_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    for c in CATEGORICAL_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    for col, v in state_mean(df).items():
        df[col] = v
        keep.append(col)
    keep = sorted(set(keep))
    out = df[keep].copy()
    out["_eligible_any"] = False
    for H in HORIZONS:
        out[f"root_within_{H}d"] = df[f"root_within_{H}d"].to_numpy()
        out[f"turn_within_{H}d"] = df[f"turn_within_{H}d"].to_numpy()
        out[f"eligible_{H}d"] = df[f"eligible_{H}d"].to_numpy()
        out["_eligible_any"] = out["_eligible_any"] | df[f"eligible_{H}d"].to_numpy()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "risk_benchmark.parquet"
    out.to_parquet(path, index=False)

    # ---- manifest ----
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {
        "source_v3f": str(V3F.relative_to(ROOT)),
        "source_wes": str(WES.relative_to(ROOT)),
        "output": str(path.relative_to(ROOT)),
        "sha256": sha,
        "rows": int(len(out)),
        "anchor": "v3f within-lifecycle rows, frozen split preserved",
        "limit_root_mm": LIMIT_ROOT,
        "horizons": [],
    }
    for H in HORIZONS:
        la = out[f"root_within_{H}d"].to_numpy()
        lb = out[f"turn_within_{H}d"].to_numpy()
        el = out[f"eligible_{H}d"].to_numpy()
        te = out["split"].eq("test").to_numpy()
        summary["horizons"].append({
            "horizon_days": H,
            "eligible": int(el.sum()),
            "eligible_test": int((el & te).sum()),
            "root_events": int((la == 1).sum()),
            "root_events_test": int(((la == 1) & te).sum()),
            "root_rate_of_eligible": round(float(la[el].mean()), 5) if el.sum() else None,
            "root_rate_of_eligible_test": round(float(la[el & te].mean()), 5) if (el & te).sum() else None,
            "turn_events": int((lb == 1).sum()),
            "turn_events_test": int(((lb == 1) & te).sum()),
            "turn_rate_of_eligible": round(float(lb[el].mean()), 5) if el.sum() else None,
            "turn_rate_of_eligible_test": round(float(lb[el & te].mean()), 5) if (el & te).sum() else None,
            "excluded_unknown_followup": int((~el).sum()),
        })
    (OUTPUT / "risk_benchmark_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
