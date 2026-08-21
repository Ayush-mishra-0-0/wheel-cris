"""Materialize point-in-time free-delta evidence from the current WES artifact."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from models.phase5.wes_paths import current_wes_path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "model_datasets" / "v5"
OUT = OUT_DIR / "free_delta_features_v1.parquet"
MANIFEST = OUT_DIR / "free_delta_features_v1_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    source = current_wes_path()
    columns = [
        "measurement_record_id", "wheelset_equipment_id", "measurement_timestamp",
        "wsmFlangeThickness1", "wsmFlangeThickness2", "wsmRoot1", "wsmRoot2",
        "wsmWheelGauge1", "wsmWheelGauge2", "wsmTireThikness1", "wsmTireThikness2",
        "skid_turn_record_at_measurement",
    ]
    frame = pd.read_parquet(source, columns=columns)
    frame["measurement_timestamp"] = pd.to_datetime(frame["measurement_timestamp"], errors="coerce")
    frame = frame.sort_values(["wheelset_equipment_id", "measurement_timestamp", "measurement_record_id"]).reset_index(drop=True)
    groups = frame.groupby("wheelset_equipment_id", sort=False)
    for name, left, right in (
        ("flange_thickness", "wsmFlangeThickness1", "wsmFlangeThickness2"),
        ("root", "wsmRoot1", "wsmRoot2"),
        ("wheel_gauge", "wsmWheelGauge1", "wsmWheelGauge2"),
        ("tire_thickness", "wsmTireThikness1", "wsmTireThikness2"),
    ):
        current = pd.concat([pd.to_numeric(frame[left], errors="coerce"), pd.to_numeric(frame[right], errors="coerce")], axis=1).mean(axis=1)
        previous = current.groupby(frame["wheelset_equipment_id"], sort=False).shift(1)
        frame[f"{name}_mean_mm"] = current
        frame[f"{name}_delta_mm"] = current - previous
    frame["days_since_previous_measurement"] = groups["measurement_timestamp"].diff().dt.total_seconds().div(86400.0)
    frame["has_prior_measurement"] = frame["days_since_previous_measurement"].notna().astype("int8")
    frame["skid_flag"] = frame["skid_turn_record_at_measurement"].fillna(0).astype("int8")
    keep = [
        "measurement_record_id", "wheelset_equipment_id", "measurement_timestamp",
        "flange_thickness_mean_mm", "flange_thickness_delta_mm", "root_mean_mm", "root_delta_mm",
        "wheel_gauge_mean_mm", "wheel_gauge_delta_mm", "tire_thickness_mean_mm", "tire_thickness_delta_mm",
        "days_since_previous_measurement", "has_prior_measurement", "skid_flag",
    ]
    result = frame[keep]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result.to_parquet(OUT, index=False)
    manifest = {
        "dataset_version": "free_delta_features_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_wes": str(source.relative_to(ROOT)),
        "source_sha256": sha256(source),
        "rows": int(len(result)),
        "delta_rule": "current same-wheelset mean minus immediately prior timestamp-ordered mean; first observation is NaN",
        "no_interpolation": True,
        "coverage": {column: round(float(result[column].notna().mean()), 6) for column in keep if column.endswith("_delta_mm")},
        "skid_flag_rows": int(result["skid_flag"].sum()),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
