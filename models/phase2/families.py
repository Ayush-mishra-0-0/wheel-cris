"""Phase 2 — shared family taxonomy for the v2.0 model dataset.

Every feature column in the v2.0 manifest (115 features) is assigned to exactly
one of 8 families. This single source of truth is used by WS1 (benchmark
metadata), WS4 (family attribution) and WS5 (family ablation) so all three
speak the same language. Assignment is deterministic from column names (prefix
rules + explicit lists) and is validated against the manifest on load.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_MANIFEST = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_manifest_v2.0.json"

# Explicit members per family (exact column names).
_EXPLICIT = {
    "behavior": ["diameter_delta_raw_mm_side_1", "diameter_delta_raw_mm_side_2"],
    "identity_temporal": ["interval_days", "wheel_position_1_12", "axle_position_1_6",
                          "wheel_age_days_proxy"],
    "maintenance": ["maintenance_jobcard_creation_count",
                    "inspection_count_through_interval_end", "wheel_profile_2class",
                    "turning_indicator_raw", "days_since_turning"],
    "operational": ["rtis_source_event_count", "rtis_source_event_type_count",
                    "rtis_reporting_coverage_pct", "rtis_report_count",
                    "rtis_reporting_days", "rtis_duplicate_report_count",
                    "home_shed__freq", "defect_division__freq"],
}

# Prefix rules (family -> tuple of prefixes). First match wins, checked in order.
_PREFIXES = [
    ("geometry", ("geom_",)),
    ("physics", ("phys_",)),
    ("exposure_v2", ("interval_distance_km", "distance_per_day_km",
                     "distance_since_last_inspection_km", "running_days",
                     "running_days_pct", "rtis_distance_coverage_days_in_interval",
                     "rtis_distance_coverage_pct_in_interval", "running_hours_proxy",
                     "maintenance_density_per_day", "maintenance_density_per_1000km",
                     "distance_since_turning_km")),
    ("physics_v2", ("wear_per_1000km_", "remaining_material_per_km_",
                    "projected_remaining_km_", "exposure_index_")),
    ("maintenance", ("wheel_schedule_id__",)),
    ("operational", ("defect_zone__",)),
]

FAMILY_ORDER = ["behavior", "geometry", "physics", "maintenance", "operational",
                "identity_temporal", "exposure_v2", "physics_v2"]

FAMILY_LABELS = {
    "behavior": "Behavior (current-interval delta)",
    "geometry": "Geometry (geom_*)",
    "physics": "Physics (phys_*)",
    "maintenance": "Maintenance",
    "operational": "Operational / legacy exposure",
    "identity_temporal": "Identity / Temporal",
    "exposure_v2": "Exposure v2 (WS1)",
    "physics_v2": "Physics v2 (WS3)",
}


def feature_families(manifest_path: Path = V2_MANIFEST) -> dict[str, list[str]]:
    """Return {family: [column, ...]} covering every feature column in the manifest."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    roles = manifest["column_roles"]
    features = [c for c, r in roles.items() if r == "feature"]

    assignment: dict[str, list[str]] = {f: [] for f in FAMILY_ORDER}
    leftover = []

    for col in features:
        matched = False
        for family, cols in _EXPLICIT.items():
            if col in cols:
                assignment[family].append(col)
                matched = True
                break
        if not matched:
            for family, prefixes in _PREFIXES:
                if any(col.startswith(p) for p in prefixes):
                    assignment[family].append(col)
                    matched = True
                    break
        if not matched:
            leftover.append(col)

    if leftover:
        raise ValueError(f"unassigned feature columns: {leftover}")

    # Validate: no column assigned twice (explicit + prefix).
    all_cols = [c for cols in assignment.values() for c in cols]
    if len(all_cols) != len(set(all_cols)):
        raise ValueError("column assigned to more than one family")
    if set(all_cols) != set(features):
        raise ValueError(f"coverage mismatch: {len(all_cols)} assigned vs {len(features)} features")
    return assignment


def all_features(manifest_path: Path = V2_MANIFEST) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [c for c, r in manifest["column_roles"].items() if r == "feature"]


if __name__ == "__main__":
    fams = feature_families()
    total = 0
    for fam in FAMILY_ORDER:
        cols = fams[fam]
        total += len(cols)
        print(f"{fam:18s} {len(cols):3d}  {FAMILY_LABELS[fam]}")
        for c in cols:
            print(f"    {c}")
    print(f"\nTOTAL: {total} features")
