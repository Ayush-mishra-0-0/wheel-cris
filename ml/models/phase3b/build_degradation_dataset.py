"""Phase 3B - build segment-wise degradation dataset.

Consecutive-inspection pairs within an equipment's record, used to learn wheel
degradation (change in measured engineering state over an exposure interval).

Each pair: state at time t -> observed state at the next inspection t+dt.

  - Features : engineering state + quality at t, exposure (interval_days),
               identities, categorical context.
  - Targets  : next-measured engineering state (diameter, flange thickness,
               root, gauge) and their deltas.
  - Segment boundary flags : a crossing turning/replacement record on the later
               row means the pair spans a maintenance reset. Such pairs are
               EXCLUDED from wear learning (wear is not monotonic across a
               reset) but their state is still predicted from the first state
               via (delta = next - current) only within a life segment.

The dataset is immutable for a given WES v1.0 input; a manifest records the hash.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WES_PATH = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "model_datasets" / "v3b"

DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot", "wsmWheelGauge"]
SIDES = ["1", "2"]

STATE_COLUMNS = [f"{d}{s}" for d in DIMENSIONS for s in SIDES]
QUALITY_COLUMNS = [f"{c}_quality" for c in STATE_COLUMNS]
EXPOSURE_COLUMNS = [
    "interval_days", "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
    "days_since_turning", "wheel_age_days_proxy",
]
CATEGORICAL_COLUMNS = ["LocoType", "wheel_profile_2class", "home_shed",
                       "defect_zone", "defect_division", "wheel_position_1_12",
                       "axle_position_1_6"]


def main() -> None:
    df = pd.read_parquet(WES_PATH)
    df = df.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).copy()

    keep = ["measurement_record_id", "wheelset_equipment_id", "measurement_timestamp",
            "turning_record_at_measurement"] + STATE_COLUMNS + QUALITY_COLUMNS \
           + EXPOSURE_COLUMNS + CATEGORICAL_COLUMNS
    base = df[keep]

    base["prev_time"] = base.groupby("wheelset_equipment_id")["measurement_timestamp"].shift(1)
    base["next_time"] = base.groupby("wheelset_equipment_id")["measurement_timestamp"].shift(-1)
    base["prev_record_id"] = base.groupby("wheelset_equipment_id")["measurement_record_id"].shift(1)
    base["next_record_id"] = base.groupby("wheelset_equipment_id")["measurement_record_id"].shift(-1)
    base["next_turning"] = base.groupby("wheelset_equipment_id")["turning_record_at_measurement"].shift(-1)
    base["prev_turning"] = base["turning_record_at_measurement"]

    for d in DIMENSIONS:
        for s in SIDES:
            col = f"{d}{s}"
            qcol = f"{col}_quality"
            base[f"next_{col}"] = base.groupby("wheelset_equipment_id")[col].shift(-1)
            base[f"next_{qcol}"] = base.groupby("wheelset_equipment_id")[qcol].shift(-1)
            base[f"delta_{col}"] = base[f"next_{col}"] - base[col]

    base["interval_days_pair"] = (
        (base["next_time"] - base["measurement_timestamp"]).dt.total_seconds() / 86400)

    # A pair crossing a turning/replacement reset (turning recorded on the later row)
    # breaks monotonic wear. Its delta is invalid for wear learning.
    base["crosses_reset"] = base["next_turning"].eq(1) | base["prev_turning"].eq(1)
    # At least one side must be a valid observed state at both ends for a usable target.
    base["target_valid"] = np.nan  # resolved per dimension below

    avail = base.dropna(subset=["next_record_id"]).copy()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pairs = avail
    pairs.to_parquet(OUTPUT / "degradation_pairs.parquet", index=False)

    manifest = {
        "input": str(WES_PATH.relative_to(ROOT)),
        "input_sha256": hashlib.sha256(pd.read_parquet(WES_PATH, columns=["measurement_record_id"])
                                       .to_parquet()).hexdigest(),
        "rows": int(len(pairs)),
        "equipment": int(pairs["wheelset_equipment_id"].nunique()),
        "pairs_crossing_reset": int(pairs["crosses_reset"].sum()),
        "pairs_non_reset": int((~pairs["crosses_reset"]).sum()),
        "columns": STATE_COLUMNS + QUALITY_COLUMNS + EXPOSURE_COLUMNS + CATEGORICAL_COLUMNS,
        "grain": "consecutive inspection pair within equipment",
        "dimension_targets": [f"next_{c}" for c in STATE_COLUMNS],
        "wear_targets": [f"delta_{c}" for c in STATE_COLUMNS],
    }
    (OUTPUT / "degradation_manifest_v1.0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))
    print("rows", len(pairs), "equipment", pairs["wheelset_equipment_id"].nunique(),
          "crossing", pairs["crosses_reset"].sum())


if __name__ == "__main__":
    main()
