"""Model Dataset builder v1.1 — v1.0 augmented with physics-informed features.

Reuses the immutable v1.0 dataset (identical rows, splits, labels) and adds the
point-in-time-safe physics features (model_datasets/physics_features.py) joined on
`interval_end_measurement_id`. Only the X matrix changes.

Outputs a new versioned directory (model_datasets/v1.1/) and never overwrites
silently; pass --force to regenerate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MODEL_DATASET_DIR = PROJECT_ROOT / "model_datasets"
V1_0_DIR = MODEL_DATASET_DIR / "v1.0"
V1_1_DIR = MODEL_DATASET_DIR / "v1.1"
PHYSICS_PATH = MODEL_DATASET_DIR / "physics" / "physics_features_v1.1.parquet"
PHYSICS_MANIFEST_PATH = MODEL_DATASET_DIR / "physics" / "physics_features_manifest_v1.1.json"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"

DATASET_VERSION = "v1.1"
AUGMENT_PREFIXES = ("phys_", "geom_")


def _load_v1_0() -> tuple[pd.DataFrame, dict]:
    dataset = pd.read_parquet(V1_0_DIR / "model_dataset_v1.0.parquet")
    manifest = json.loads((V1_0_DIR / "model_dataset_manifest_v1.0.json").read_text(encoding="utf-8"))
    return dataset, manifest


def _load_physics() -> pd.DataFrame:
    physics = pd.read_parquet(PHYSICS_PATH)
    physics["wsmId"] = physics["wsmId"].astype("Int64")
    return physics


def build_model_dataset_v1_1(force: bool = False) -> dict[str, Path]:
    if V1_1_DIR.exists() and not force:
        raise FileExistsError(f"{V1_1_DIR} already exists; use --force to regenerate (never regenerate silently)")

    dataset, v10_manifest = _load_v1_0()
    physics = _load_physics()
    physics_manifest = json.loads(PHYSICS_MANIFEST_PATH.read_text(encoding="utf-8"))

    rows_before = len(dataset)
    augmented = dataset.merge(
        physics.drop(columns=["wheelset_equipment_id", "measurement_timestamp"]),
        left_on="interval_end_measurement_id", right_on="wsmId", how="left", validate="one_to_one",
    )
    if len(augmented) != rows_before:
        raise RuntimeError(f"merge changed row count {rows_before} -> {len(augmented)}")
    matched = int(augmented["phys_remaining_material_mm_s1"].notna().sum())
    print(f"physics join: {matched:,}/{rows_before:,} rows matched ({matched / rows_before * 100:.2f}%)")

    # Restore eda_context columns (home_shed/defect_*) from the feature store —
    # v1.0 dropped the raw categoricals after encoding, but they are needed for
    # error analysis / slicing and are recorded as eda_context in the roles.
    eda_context = [c for c, role in v10_manifest["column_roles"].items() if role == "eda_context"]
    if eda_context and not all(c in augmented.columns for c in eda_context):
        store_ctx = pd.read_parquet(STORE_PATH, columns=["operational_exposure_id", *eda_context])
        augmented = augmented.merge(store_ctx, on="operational_exposure_id", how="left", validate="one_to_one")
        if len(augmented) != rows_before:
            raise RuntimeError(f"eda_context merge changed row count")

    # Physics + geometry columns become numeric X features. Impute NA on TRAIN
    # median only (consistent with v1.0 numeric policy) and drop the join key.
    aug_cols = [c for c in augmented.columns if c.startswith(AUGMENT_PREFIXES)]
    train_medians = augmented.loc[augmented["split"] == "train", aug_cols].median()
    for col in aug_cols:
        augmented[col] = augmented[col].fillna(train_medians[col])

    # Rebuild column roles: everything from v1.0 stays; aug columns join X.
    roles = dict(v10_manifest["column_roles"])
    for col in aug_cols:
        roles[col] = "feature"
    roles.pop("wsmId", None)

    # Validation gate: X must remain fully populated and no label may leak in.
    x_columns = [c for c, role in roles.items() if role == "feature"]
    y_columns = [c for c, role in roles.items() if role == "label"]
    na_cells = int(augmented[x_columns].isna().sum().sum())
    if na_cells != 0:
        raise RuntimeError(f"X has {na_cells} NA cells after imputation")
    leaked = [c for c in y_columns if c in x_columns]
    if leaked:
        raise RuntimeError(f"label leakage into features: {leaked}")
    constants = [c for c in x_columns if augmented[c].nunique(dropna=True) <= 1]
    if constants:
        raise RuntimeError(f"constant X columns: {constants}")

    out_manifest = dict(v10_manifest)
    out_manifest["dataset_version"] = DATASET_VERSION
    out_manifest["parent_dataset_version"] = "v1.0"
    out_manifest["physics_version"] = physics_manifest["physics_version"]
    out_manifest["physics_constants"] = physics_manifest["constants"]
    out_manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    out_manifest["x_columns"] = x_columns
    out_manifest["column_roles"] = roles
    out_manifest["physics_added_columns"] = [c for c in aug_cols if c.startswith("phys_")]
    out_manifest["geometry_added_columns"] = [c for c in aug_cols if c.startswith("geom_")]
    out_manifest["physics_join_match_pct"] = round(matched / rows_before * 100, 4)

    V1_1_DIR.mkdir(parents=True, exist_ok=True)
    augmented.to_parquet(V1_1_DIR / "model_dataset_v1.1.parquet", index=False)
    (V1_1_DIR / "model_dataset_manifest_v1.1.json").write_text(json.dumps(out_manifest, indent=2) + "\n", encoding="utf-8")
    for name in ("train", "val", "test"):
        augmented[augmented["split"] == name].to_parquet(V1_1_DIR / f"{name}_v1.1.parquet", index=False)

    summary = [
        f"# Dataset Card — model dataset {DATASET_VERSION}",
        "",
        f"- **Parent:** v1.0 (immutable; rows/splits/labels identical)",
        f"- **Rows (supervised):** {rows_before:,}",
        f"- **Features (X):** {len(x_columns)} (v1.0: {len(v10_manifest['x_columns'])} + augmentation: {len(aug_cols)})",
        f"- **Physics join match:** {matched:,} rows ({matched / rows_before * 100:.2f}%)",
        "",
        "## Augmentation feature groups (point-in-time safe, as-of interval end)",
        "",
        "| Group | Columns |",
        "| --- | --- |",
    ]
    groups = {
        "Raw measured geometry at interval end (geom_*)": [c for c in aug_cols if c.startswith("geom_")],
        "Level 1 material state": [c for c in aug_cols if c.startswith("phys_") and any(s in c for s in ["remaining_material", "wear_fraction", "material_consumed_pct", "initial_dia"])],
        "Level 2 wear trends": [c for c in aug_cols if c.startswith("phys_") and any(s in c for s in ["cumulative_wear", "interval_wear_rate", "wear_acceleration", "ema_wear_rate", "remaining_budget_days"])],
        "Life-cycle state": [c for c in aug_cols if c.startswith("phys_") and any(s in c for s in ["turning_events_cumulative", "wheelset_age_days"])],
    }
    for group_name, members in groups.items():
        summary.append(f"| {group_name} | {', '.join(members) if members else '(none)'} |")
    summary += [
        "",
        f"- Physics constants: condemning dia = {physics_manifest['constants']['condemning_dia_mm']} mm, new dia = {physics_manifest['constants']['dia_plausible'][1]} mm (domain-provided).",
        "- geom_* columns are the absolute measured wheel geometry at interval_end (the prediction timestamp) — previously excluded from v1.0, which carried only interval deltas.",
        "- NA imputed with TRAIN median (same policy as v1.0 numeric features).",
    ]
    (V1_1_DIR / "dataset_card.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"v1.1 dataset written: {V1_1_DIR}")
    return {"dataset": V1_1_DIR / "model_dataset_v1.1.parquet", "manifest": V1_1_DIR / "model_dataset_manifest_v1.1.json", "card": V1_1_DIR / "dataset_card.md"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, path in build_model_dataset_v1_1(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
