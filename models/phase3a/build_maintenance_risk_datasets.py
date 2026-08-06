"""Phase 3A - build maintenance-risk benchmark datasets.

Combines the frozen Wheel Engineering State v1.0 features with fixed-horizon
labels defined by the Maintenance Event Specification and gated by the Target
Eligibility Matrix.

For each measurement-state row (one attributable inspection) and each horizon H,
the row is labelled:

    eligible       = follow_up_days >= H  OR  (turning event within H)
    label('within_HD') = 1 if a (equipment-day) turning event day falls strictly
                              inside (measurement_time, measurement_time + H]
    label('within_HD') = 0 if eligible and no event inside the window
    excluded          = follow_up_days < H and no event inside the window
                        (Unknown follow-up: row dropped from that horizon)

Only the state fields observable at measurement time are retained as features.
The measurement identity/time are kept for provenance but are not model features.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WES_PATH = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
BRONZE_PATH = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUTPUT = ROOT / "model_datasets" / "v3a"
HORIZONS = (30, 90, 180, 365)

# Features observable at measurement time. Blocked/margin/health fields and the
# event indicator itself are intentionally excluded (they are semantics-blocked or
# are the target).
FEATURE_COLUMNS = [
    "wsmDia1", "wsmDia2",
    "wsmFlangeThickness1", "wsmFlangeThickness2",
    "wsmRoot1", "wsmRoot2",
    "wsmTireThikness1", "wsmTireThikness2",
    "wsmWheelGauge1", "wsmWheelGauge2",
    "interval_days", "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
    "wheel_position_1_12", "axle_position_1_6", "wheel_age_days_proxy",
    "days_since_turning", "interval_context_available",
]
CATEGORICAL_COLUMNS = ["LocoType", "wheel_profile_2class", "home_shed",
                       "defect_zone", "defect_division"]


def _event_days_by_equipment(turns: pd.DataFrame) -> dict[int, np.ndarray]:
    event_days = turns.drop_duplicates(["equipment", "day"])
    return {
        equipment: group["day"].to_numpy(dtype="datetime64[ns]")
        for equipment, group in event_days.groupby("equipment", sort=False)
    }


def main() -> None:
    wes = pd.read_parquet(WES_PATH)
    bronze = pd.read_parquet(BRONZE_PATH, columns=["wsmEquipmentId", "wsmUpdatedOn", "wsmturning1"])

    bronze = bronze.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).copy()
    bronze["equipment"] = bronze["wsmEquipmentId"].astype("int64")
    bronze["time"] = pd.to_datetime(bronze["wsmUpdatedOn"])
    turns = bronze.loc[bronze["wsmturning1"].eq(1), ["equipment", "time"]].copy()
    turns["day"] = turns["time"].dt.normalize()
    event_days = _event_days_by_equipment(turns)
    obs_end = bronze.groupby("equipment", sort=False)["time"].max()

    df = wes.rename(columns={"wheelset_equipment_id": "equipment",
                             "measurement_timestamp": "time"}).copy()
    df["equipment"] = df["equipment"].astype("int64")
    df["time"] = pd.to_datetime(df["time"])
    n_before = len(df)

    df["observation_end"] = df["equipment"].map(obs_end)
    df["followup_days"] = (df["observation_end"] - df["time"]).dt.total_seconds() / 86400

    equip_codes = df["equipment"].to_numpy()
    time_values = df["time"].to_numpy(dtype="datetime64[ns]")
    look = {int(k): v for k, v in event_days.items()}

    base_cols = ["measurement_record_id", "equipment", "time", "followup_days"] \
                + FEATURE_COLUMNS + CATEGORICAL_COLUMNS
    base = df[base_cols].reset_index(drop=True)

    summary = {"source": str(WES_PATH.relative_to(ROOT)),
               "total_state_rows": int(n_before),
               "horizons": []}
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for horizon in HORIZONS:
        event_within = np.zeros(len(base), dtype=bool)
        for equipment, dates in look.items():
            mask = equip_codes == equipment
            if not mask.any():
                continue
            start = time_values[mask]
            left = np.searchsorted(dates, start, side="right")
            right = np.searchsorted(dates, start + np.timedelta64(horizon, "D"), side="right")
            event_within[mask] = right > left

        full_window = base["followup_days"].to_numpy() >= horizon
        eligible = event_within | full_window
        label = event_within.astype(float)
        label[~eligible] = np.nan  # excluded rows carry no label for this horizon

        ds = base.copy()
        ds[f"within_{horizon}d"] = label
        ds["eligible"] = eligible

        prefix = f"turn_within_{horizon}d"
        path = OUTPUT / f"{prefix}.parquet"
        ds.to_parquet(path, index=False)

        summary["horizons"].append({
            "horizon_days": horizon,
            "rows": int(len(ds)),
            "eligible": int(eligible.sum()),
            "eligible_fraction": float(eligible.mean()),
            "events": int(event_within.sum()),
            "event_rate_of_eligible": float(event_within.sum() / max(eligible.sum(), 1)),
            "excluded_unknown_followup": int((~eligible).sum()),
            "file": path.name,
        })
        print(f"  {prefix:18s} eligible={int(eligible.sum()):,} "
              f"events={int(event_within.sum()):,} rate={event_within.mean():.4f}")

    (OUTPUT / "maintenance_risk_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
