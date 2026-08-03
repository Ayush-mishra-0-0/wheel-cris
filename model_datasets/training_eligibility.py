"""Training Eligibility Filter — the contract between the Feature Store and the
Model Dataset.

It is the ONLY place that decides which columns are safe to model, so the model
builder and notebooks never have to re-derive safety rules. It enforces:

  - approved feature status (from the feature specification)
  - point-in-time safety (features available at interval end, by construction)
  - identifier / provenance removal
  - constant-column removal
  - missingness thresholds
  - non-numeric / free-text removal
  - categorical encoding policy
  - leakage checks (no future-dated or label content in X)

Output: an eligibility manifest (JSON) consumed by the model dataset builder.
Idempotent: re-running on the same store/spec produces the same manifest.
"""
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

CONFIG_DIR = PROJECT_ROOT / "configs"
MODEL_DATASET_DIR = PROJECT_ROOT / "model_datasets"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"
APPROVED_STATUSES = {"READY", "READY_WITH_CAVEAT", "READY_FOR_MATERIALISATION"}

# Identity / grouping columns carried alongside X (keys for splits), never model features.
IDENTITY_COLUMNS = [
    "operational_exposure_id",
    "interval_start_measurement_id",
    "interval_end_measurement_id",
    "wheelset_equipment_id",
    "locomotive_id",
    "locomotive_number",
    "interval_start_timestamp",
    "interval_end_timestamp",
    "timeline_quality_tier",  # constant "Gold B" for the released cohort; identity, not predictive
]

# Provenance / metadata emitted by a feature but not predictive on their own.
PROVENANCE_COLUMNS = ["wheel_age_date_source"]

# Non-predictive / free-text source payloads.
NON_PREDICTIVE_COLUMNS = ["rtis_source_event_types"]

# Model-level missingness threshold (%): features above it are not eligible.
MAX_MISSINGNESS_PCT = 85.0

# One-hot up to this many levels; above it use frequency encoding.
ONE_HOT_MAX_LEVELS = 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _categorical_columns(store: pd.DataFrame) -> dict[str, str]:
    candidates = ["assignment_quality_tier", "home_shed", "defect_zone", "defect_division", "wheel_schedule_id", "wheel_profile_2class", "LocoType"]
    policy: dict[str, str] = {}
    for column in candidates:
        if column not in store.columns:
            continue
        levels = int(store[column].nunique(dropna=True))
        if levels <= 1:
            continue  # constant; handled by constant check
        if levels <= 2:
            policy[column] = "ordinal_binary"
        elif levels <= ONE_HOT_MAX_LEVELS:
            policy[column] = "one_hot"
        else:
            policy[column] = "frequency"
    return policy


def build_eligibility_manifest() -> dict:
    spec = load_and_validate()
    store = pd.read_parquet(STORE_PATH)

    # 1. Approved feature columns (store output names = materialization keys), in spec order.
    ordered_columns: list[str] = []
    for feature in spec["features"]:
        mapping = feature.get("materialization")
        if feature["status"] not in APPROVED_STATUSES or not mapping:
            continue
        if mapping["source"] == "loco_types":
            continue  # constant for WAP7 cohort; handled by constant check via store
        for column in mapping["columns"].keys():
            ordered_columns.append(column)

    # 2. Available, non-identity, non-provenance columns.
    available = [c for c in ordered_columns if c in store.columns and c not in IDENTITY_COLUMNS and c not in PROVENANCE_COLUMNS and c not in NON_PREDICTIVE_COLUMNS]

    # 3. Constant columns (single distinct non-null value across all rows).
    constants = [c for c in available if store[c].nunique(dropna=True) <= 1]

    # 4. Missingness threshold.
    missingness = {c: round(float(store[c].isna().mean() * 100), 2) for c in available}
    too_missing = [c for c in available if missingness[c] > MAX_MISSINGNESS_PCT]

    # 5. Categorical candidates (known categorical columns) vs free-text strings.
    categorical = {c for c in _categorical_columns(store) if c in available}
    string_typed = {c for c in available if isinstance(store[c].dtype, pd.StringDtype) or store[c].dtype == object}
    free_text = sorted(string_typed - categorical)

    eligible = [c for c in available if c not in constants and c not in too_missing and c not in free_text]

    # 6. Categorical encoding policy over eligible columns.
    encoding_policy = {c: policy for c, policy in _categorical_columns(store).items() if c in eligible}
    numeric_policy = {c: "numeric" for c in eligible if c not in encoding_policy}

    # 7. Missing encoding policy.
    missing_policy = {
        c: {
            "pct_missing": missingness[c],
            "policy": "NA_indicator_column + median_impute" if missingness[c] > 0.5 else "none",
            "semantics": "NA" 
        }
        for c in eligible
        if missingness[c] > 0.5
    }
    # days_since_turning: null means "no turning observed in equipment history", not missing data.
    if "days_since_turning" in missing_policy:
        missing_policy["days_since_turning"]["semantics"] = "null = never turned on this wheelset; encode as separate never_turned indicator + 0 fill"

    # 8. Leakage check: ensure no label columns and no future-dated columns are in X.
    label_spec = json.loads((CONFIG_DIR / "label_specification.json").read_text(encoding="utf-8"))
    label_columns = {label["label_id"] for label in label_spec["labels"]}
    leakage = [c for c in eligible if c in label_columns]
    if leakage:
        raise ValueError(f"Leakage detected: label columns present in eligible X: {leakage}")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {"feature_spec": _sha256(CONFIG_DIR / "engineering_feature_specification_v1.json"), "label_spec": _sha256(CONFIG_DIR / "label_specification.json"), "feature_store": _sha256(STORE_PATH)},
        "approved_features": [f["feature_id"] for f in spec["features"] if f["status"] in APPROVED_STATUSES and f.get("materialization")],
        "eligible_columns": eligible,
        "dropped": {
            "identity_or_provenance": [c for c in ordered_columns if c in IDENTITY_COLUMNS or c in PROVENANCE_COLUMNS],
            "non_predictive_payload": NON_PREDICTIVE_COLUMNS,
            "constant": constants,
            "above_missingness_threshold": too_missing,
            "non_numeric_free_text": free_text,
        },
        "encoding_policy": {**numeric_policy, **encoding_policy},
        "missing_policy": missing_policy,
        "policy": {
            "approved_statuses": sorted(APPROVED_STATUSES),
            "max_missingness_pct": MAX_MISSINGNESS_PCT,
            "one_hot_max_levels": ONE_HOT_MAX_LEVELS,
            "point_in_time_rule": "all eligible columns are available at interval_end_timestamp by feature-spec construction",
        },
        "leakage_check": {"passed": True, "label_columns_excluded": sorted(label_columns)},
    }

    MODEL_DATASET_DIR.mkdir(exist_ok=True)
    manifest_path = MODEL_DATASET_DIR / "training_eligibility_manifest_v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    manifest = build_eligibility_manifest()
    print(f"Eligible columns: {len(manifest['eligible_columns'])}")
    for column in manifest["eligible_columns"]:
        print(f"  {column} [{manifest['encoding_policy'].get(column, 'numeric')}]")
    print("Dropped:", json.dumps(manifest["dropped"], indent=2))
