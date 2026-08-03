"""Materialise Feature Store v1.0 from the approved feature specification."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from silver_gold.validate_feature_specification import load_and_validate  # noqa: E402

STORE_DIR = PROJECT_ROOT / "feature_store"
APPROVED_STATUSES = {"READY", "READY_WITH_CAVEAT", "READY_FOR_MATERIALISATION"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_feature_store() -> dict[str, Path]:
    """Build an interval-grain store exclusively from approved specifications."""
    spec = load_and_validate()
    approved = [item for item in spec["features"] if item["status"] in APPROVED_STATUSES]
    unapproved = [item for item in spec["features"] if item["status"] not in APPROVED_STATUSES]
    missing_mapping = [item["feature_id"] for item in approved if "materialization" not in item]
    if missing_mapping:
        raise ValueError(f"Approved features require materialization mappings: {missing_mapping}")

    exposure_path = PROJECT_ROOT / "data/gold/operational_exposure/v1.0/inspection_interval_operational_exposure.parquet"
    interval_path = PROJECT_ROOT / "data/gold/inspection_intervals/v1.0/inspection_intervals_gold_b.parquet"
    interval_context_path = PROJECT_ROOT / "data/gold/interval_context/v1.0/inspection_interval_context.parquet"
    loco_type_path = PROJECT_ROOT / "data/bronze/loco_types.parquet"
    exposure = pd.read_parquet(exposure_path)
    intervals = pd.read_parquet(interval_path)
    interval_context = pd.read_parquet(interval_context_path)
    identity_columns = ["interval_start_measurement_id", "interval_end_measurement_id", "timeline_quality_tier", "LocoType"]
    if intervals.duplicated(["interval_start_measurement_id", "interval_end_measurement_id"]).any():
        raise ValueError("Inspection interval keys must be unique for Feature Store v1.0")
    store = exposure[["operational_exposure_id", "interval_start_measurement_id", "interval_end_measurement_id", "wheelset_equipment_id", "locomotive_id", "locomotive_number", "interval_start_timestamp", "interval_end_timestamp"]].merge(
        intervals[identity_columns], on=["interval_start_measurement_id", "interval_end_measurement_id"], how="left", validate="one_to_one"
    )
    sources = {"operational_exposure": exposure, "inspection_intervals": intervals, "interval_context": interval_context}
    materialised: list[dict] = []
    for feature in approved:
        mapping = feature["materialization"]
        source = mapping["source"]
        if source == "loco_types":
            lookup = pd.read_parquet(loco_type_path)
            lookup = lookup[["LotTypeName", *mapping["columns"].values()]].rename(columns={value: key for key, value in mapping["columns"].items()})
            store = store.merge(lookup, left_on="LocoType", right_on="LotTypeName", how="left", validate="many_to_one").drop(columns=["LotTypeName"])
        else:
            source_frame = sources[source]
            keys = ["interval_start_measurement_id", "interval_end_measurement_id"]
            source_columns = list(mapping["columns"].values())
            available = source_frame[keys + source_columns].copy()
            available = available.rename(columns={value: key for key, value in mapping["columns"].items()})
            store = store.merge(available, on=keys, how="left", validate="one_to_one")
        materialised.append({"feature_id": feature["feature_id"], "status": feature["status"], "evidence_level": feature["evidence_level"], "columns": list(mapping["columns"].keys())})

    feature_columns = [column for item in materialised for column in item["columns"]]
    coverage = {column: {"non_null_rows": int(store[column].notna().sum()), "coverage_pct": round(float(store[column].notna().mean() * 100), 4)} for column in feature_columns}
    quality = {
        "row_count": len(store), "duplicate_feature_store_keys": int(store.duplicated(["operational_exposure_id"]).sum()),
        "null_locomotive_id": int(store["locomotive_id"].isna().sum()), "approved_feature_count": len(approved),
        "excluded_feature_count": len(unapproved), "excluded_by_status": pd.Series([item["status"] for item in unapproved]).value_counts().to_dict(),
        "quality_verdict": "PASS" if not store.duplicated(["operational_exposure_id"]).any() else "FAIL"
    }
    registry = {"feature_specification_id": spec["specification_id"], "feature_specification_version": spec["specification_version"], "approved_statuses": sorted(APPROVED_STATUSES), "materialised_features": materialised, "excluded_features": [{"feature_id": item["feature_id"], "status": item["status"], "reason": "status_not_approved_for_feature_store"} for item in unapproved]}
    lineage = {"feature_store_version": "1.0.0", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "input_sha256": {"feature_specification": _sha256(PROJECT_ROOT / "configs/engineering_feature_specification_v1.json"), "operational_exposure": _sha256(exposure_path), "inspection_intervals": _sha256(interval_path), "interval_context": _sha256(interval_context_path), "loco_types": _sha256(loco_type_path)}, "point_in_time_rule": spec["governance"]["point_in_time_rule"], "grain": "one released Gold-B inspection interval"}
    documentation = ["# Generated Feature Store v1.0 catalog", "", "Generated from `configs/engineering_feature_specification_v1.json`; do not edit manually.", "", "| Feature | Status | Evidence | Owner | Formula |", "| --- | --- | --- | --- | --- |"]
    for feature in approved:
        documentation.append(f"| {feature['name']} | {feature['status']} | {feature['evidence_level']} | {feature['owning_layer']} | {feature['formula']} |")

    STORE_DIR.mkdir(exist_ok=True)
    outputs = {
        "feature_store": STORE_DIR / "feature_store_v1.parquet", "feature_registry": STORE_DIR / "feature_registry.json",
        "lineage": STORE_DIR / "lineage.json", "coverage": STORE_DIR / "coverage.json", "feature_quality": STORE_DIR / "feature_quality.json",
        "documentation": STORE_DIR / "feature_catalog_generated.md"
    }
    store.to_parquet(outputs["feature_store"], index=False)
    outputs["feature_registry"].write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    outputs["lineage"].write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8")
    outputs["coverage"].write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    outputs["feature_quality"].write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8")
    outputs["documentation"].write_text("\n".join(documentation) + "\n", encoding="utf-8")
    return outputs


if __name__ == "__main__":
    for name, path in build_feature_store().items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
