"""Dependency-free CI validation for the Engineering Feature Specification."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "configs" / "engineering_feature_specification_v1.json"
ALLOWED_STATUSES = {"READY", "READY_WITH_CAVEAT", "READY_FOR_MATERIALISATION", "PENDING", "BLOCKED", "FUTURE"}
REQUIRED = {"feature_id", "name", "owning_layer", "status", "evidence_level", "version", "grain", "engineering_meaning", "formula", "unit", "lineage", "validation_rules", "availability_time", "dependencies", "consumer_limit"}
ALLOWED_EVIDENCE_LEVELS = {"Measured", "Observed", "Derived", "Physics", "ML", "Decision"}


def validate_specification(spec: dict) -> list[str]:
    errors: list[str] = []
    features = spec.get("features", [])
    ids = [item.get("feature_id") for item in features]
    if len(ids) != len(set(ids)):
        errors.append("feature_id values must be unique")
    for feature in features:
        identifier = feature.get("feature_id", "<missing>")
        missing = REQUIRED - set(feature)
        if missing:
            errors.append(f"{identifier}: missing required fields {sorted(missing)}")
        if feature.get("status") not in ALLOWED_STATUSES:
            errors.append(f"{identifier}: invalid status")
        if feature.get("evidence_level") not in ALLOWED_EVIDENCE_LEVELS:
            errors.append(f"{identifier}: invalid evidence_level")
        if not feature.get("lineage"):
            errors.append(f"{identifier}: lineage is required")
        if feature.get("status") == "BLOCKED" and not feature.get("dependencies"):
            errors.append(f"{identifier}: blocked feature requires dependencies")
        if feature.get("status") == "BLOCKED" and "No numerical output" not in feature.get("consumer_limit", "") and "Must remain null" not in feature.get("consumer_limit", ""):
            errors.append(f"{identifier}: blocked feature must prohibit materialisation")
    return errors


def load_and_validate(path: Path = SPEC_PATH) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_specification(spec)
    if errors:
        raise ValueError("Engineering Feature Specification validation failed:\n- " + "\n- ".join(errors))
    return spec


if __name__ == "__main__":
    specification = load_and_validate()
    print(f"Valid: {specification['specification_id']} {specification['specification_version']} ({len(specification['features'])} features)")
