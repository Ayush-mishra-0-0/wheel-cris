"""One-time, idempotent migration: enrich the engineering feature specification
with production metadata and correct status taxonomy.

Adds per-feature fields:
  - feature_family        : Geometry / Maintenance / Operational / Temporal /
                            Identity / Route / Environment / Physics / Health
  - point_in_time_safe    : true for every feature available at interval end
  - expected_missing_pct  : measured max missingness across the feature's
                            materialised store columns (null until released)

Also moves `wheel_health_index` from BLOCKED to FUTURE: it is a designed
engineering construct deferred to a later release, not a feature blocked by
missing/ambiguous prerequisites (the BLOCKED/FUTURE distinction of 2026-08-03).

Idempotent: safe to re-run; existing fields are preserved.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "configs" / "engineering_feature_specification_v1.json"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"

FEATURE_FAMILY = {
    "interval_days": "Temporal",
    "assignment_quality_tier": "Identity",
    "diameter_delta_raw_mm": "Geometry",
    "rtis_source_event_count": "Operational",
    "maintenance_jobcard_creation_count": "Maintenance",
    "rtis_reporting_coverage_pct": "Operational",
    "static_locomotive_axle_load": "Physics",
    "wheel_position_1_12": "Identity",
    "axle_position_1_6": "Identity",
    "inspection_count_through_interval_end": "Maintenance",
    "wheel_profile_2class": "Maintenance",
    "wheel_schedule_id": "Maintenance",
    "home_shed": "Operational",
    "defect_zone": "Route",
    "defect_division": "Route",
    "wheel_age_days_proxy": "Temporal",
    "turning_indicator_raw": "Maintenance",
    "days_since_turning": "Maintenance",
    "wear_rate_mm_per_day": "Geometry",
    "interval_distance_km": "Operational",
    "wear_rate_mm_per_km": "Geometry",
    "weather_exposure_index": "Environment",
    "curve_severity_index": "Route",
    "wheel_health_index": "Health",
}

META_COLUMNS = {"operational_exposure_id", "interval_start_measurement_id", "interval_end_measurement_id", "wheelset_equipment_id", "locomotive_id", "locomotive_number", "interval_start_timestamp", "interval_end_timestamp", "timeline_quality_tier", "LocoType"}


def _measured_missingness() -> dict[str, float]:
    store = pd.read_parquet(STORE_PATH)
    missing: dict[str, float] = {}
    for column in store.columns:
        if column in META_COLUMNS:
            continue
        pct = float(store[column].isna().mean() * 100)
        if pct > 0.05:
            missing[column] = round(pct, 2)
    return missing


def enrich(spec_path: Path = SPEC_PATH) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    measured = _measured_missingness()

    for feature in spec["features"]:
        feature["feature_family"] = FEATURE_FAMILY[feature["feature_id"]]
        feature["point_in_time_safe"] = True
        feature["expected_missing_pct"] = None
        mapping = feature.get("materialization")
        if mapping and mapping["source"] != "loco_types":
            cols = list(mapping["columns"].values())
            feature["expected_missing_pct"] = max((measured.get(c, 0.0) for c in cols), default=0.0)
        if feature["feature_id"] == "wheel_health_index":
            feature["status"] = "FUTURE"
            feature["version"] = "2.0.0"

    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return spec


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    enriched = enrich()
    from silver_gold.validate_feature_specification import load_and_validate

    validated = load_and_validate()
    print(f"Enriched OK: {len(validated['features'])} features; wheel_health_index status={[f['status'] for f in validated['features'] if f['feature_id']=='wheel_health_index'][0]}")
