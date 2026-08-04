"""Model Dataset builder v1.2 — Label cleanup (quarantined sentinel labels).

Applies label spec 1.0.1 quarantine rule on top of the immutable v1.1 dataset:

    Quarantine a supervised row if wsmDia1 of interval_end_measurement_id OR
    next_interval_end_measurement_id is outside [1000.0, 1100.0] mm.

Design: X matrix and split assignment are carried over UNCHANGED from v1.1 for
the retained rows (byte-identical features, same wheelset-grouped temporal
split), so the only delta vs v1.1 is the row set / label set. This preserves the
clean same-split comparison (test: 28,066 -> 28,065 rows) that v1.1 -> v1.2
reporting needs. Sentinel membership is derived from bronze wheel_measurements
wsmDia1 by measurement id (not a hardcoded row list).

Outputs a new versioned directory (model_datasets/v1.2/) and never overwrites
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

from silver_gold.transform import _sha256  # noqa: E402

MODEL_DATASET_DIR = PROJECT_ROOT / "model_datasets"
V1_1_DIR = MODEL_DATASET_DIR / "v1.1"
V1_2_DIR = MODEL_DATASET_DIR / "v1.2"
MEASUREMENTS_PATH = PROJECT_ROOT / "data" / "bronze" / "wheel_measurements.parquet"
LABEL_SPEC_PATH = PROJECT_ROOT / "configs" / "label_specification_v1.0.1.json"

DATASET_VERSION = "v1.2"
PARENT_VERSION = "v1.1"
QUARANTINE_LO, QUARANTINE_HI = 1000.0, 1100.0


def _load() -> tuple[pd.DataFrame, dict]:
    dataset = pd.read_parquet(V1_1_DIR / "model_dataset_v1.1.parquet")
    manifest = json.loads((V1_1_DIR / "model_dataset_manifest_v1.1.json").read_text(encoding="utf-8"))
    return dataset, manifest


def _quarantine_mask(df: pd.DataFrame) -> pd.Series:
    """True where either label endpoint measurement has non-physical wsmDia1."""
    meas = pd.read_parquet(MEASUREMENTS_PATH, columns=["wsmId", "wsmDia1"])
    meas["wsmId"] = pd.to_numeric(meas["wsmId"], errors="coerce")
    meas["wsmDia1"] = pd.to_numeric(meas["wsmDia1"], errors="coerce")
    dia = meas.set_index("wsmId")["wsmDia1"]

    end = dia.reindex(df["interval_end_measurement_id"].to_numpy()).to_numpy()
    nxt = dia.reindex(df["next_interval_end_measurement_id"].to_numpy()).to_numpy()
    bad = (end < QUARANTINE_LO) | (end > QUARANTINE_HI) | \
          (nxt < QUARANTINE_LO) | (nxt > QUARANTINE_HI)
    return pd.Series(bad, index=df.index)


def build_model_dataset_v1_2(force: bool = False) -> dict[str, Path]:
    if V1_2_DIR.exists() and not force:
        raise FileExistsError(f"{V1_2_DIR} already exists; use --force to regenerate (never regenerate silently)")

    dataset, v11_manifest = _load()
    label_spec = json.loads(LABEL_SPEC_PATH.read_text(encoding="utf-8"))
    if label_spec["label_specification_version"] != "1.0.1":
        raise RuntimeError(f"expected label spec 1.0.1, got {label_spec['label_specification_version']}")

    mask = _quarantine_mask(dataset)
    rows_before = len(dataset)
    quarantined = int(mask.sum())
    got = {s: int((mask & (dataset["split"] == s)).sum()) for s in ("train", "val", "test")}
    dataset = dataset[~mask].copy()
    dataset.reset_index(drop=True, inplace=True)

    expected = {"train": 55, "val": 9, "test": 1}
    if got != expected:
        print(f"WARNING: quarantined counts {got} != audit {expected}")

    # Sanity gate identical to v1.1: X fully populated, no label leakage, no constants.
    roles = v11_manifest["column_roles"]
    x_columns = [c for c, role in roles.items() if role == "feature"]
    y_columns = [c for c, role in roles.items() if role == "label"]
    na_cells = int(dataset[x_columns].isna().sum().sum())
    if na_cells != 0:
        raise RuntimeError(f"X has {na_cells} NA cells")
    leaked = [c for c in y_columns if c in x_columns]
    if leaked:
        raise RuntimeError(f"label leakage into features: {leaked}")
    constants = [c for c in x_columns if dataset[c].nunique(dropna=True) <= 1]
    if constants:
        raise RuntimeError(f"constant X columns: {constants}")

    max_abs_label = float(dataset["next_interval_dia_delta_mm"].abs().max())
    if max_abs_label > 100:
        raise RuntimeError(f"|label| still exceeds 100 after quarantine: {max_abs_label}")

    out_manifest = dict(v11_manifest)
    out_manifest["dataset_version"] = DATASET_VERSION
    out_manifest["parent_dataset_version"] = PARENT_VERSION
    out_manifest["label_spec_version"] = label_spec["label_specification_version"]
    out_manifest["label_spec_path"] = str(LABEL_SPEC_PATH.relative_to(PROJECT_ROOT))
    out_manifest["quarantine_rule"] = label_spec["governance"]["quarantine_rule"]
    out_manifest["quarantine_counts"] = {s: got[s] for s in ("train", "val", "test")}
    out_manifest["rows_after_quarantine"] = int(len(dataset))
    out_manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    out_manifest["input_sha256"] = {
        "parent_dataset_v1.1": _sha256(V1_1_DIR / "model_dataset_v1.1.parquet"),
        "wheel_measurements": _sha256(MEASUREMENTS_PATH),
        "label_spec_1.0.1": _sha256(LABEL_SPEC_PATH),
    }
    out_manifest["split_rows"] = {name: int((dataset["split"] == name).sum()) for name in ("train", "val", "test")}
    out_manifest["max_abs_dia_delta_after_quarantine"] = max_abs_label
    out_manifest.pop("physics_join_match_pct", None)

    V1_2_DIR.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(V1_2_DIR / "model_dataset_v1.2.parquet", index=False)
    (V1_2_DIR / "model_dataset_manifest_v1.2.json").write_text(json.dumps(out_manifest, indent=2) + "\n", encoding="utf-8")
    for name in ("train", "val", "test"):
        dataset[dataset["split"] == name].to_parquet(V1_2_DIR / f"{name}_v1.2.parquet", index=False)

    card = [
        f"# Dataset Card — model dataset {DATASET_VERSION}",
        "",
        f"- **Parent:** {PARENT_VERSION} (immutable; X matrix + split assignment identical for retained rows)",
        f"- **Rows (supervised):** {len(dataset):,}  (was {rows_before:,}; {quarantined:,} quarantined)",
        f"- **Features (X):** {len(x_columns)} (unchanged from v1.1)",
        f"- **Label spec:** {label_spec['label_specification_version']} — quarantine rule `{label_spec['governance']['quarantine_rule']['id']}`",
        f"- **Quarantine rule:** wsmDia1 of `interval_end_measurement_id` OR `next_interval_end_measurement_id` outside [{QUARANTINE_LO:g}, {QUARANTINE_HI:g}] mm",
        f"- **Quarantined by split:** train {got['train']} · val {got['val']} · test {got['test']}",
        f"- **Split rows:** train={int((dataset['split']=='train').sum()):,} · val={int((dataset['split']=='val').sum()):,} · test={int((dataset['split']=='test').sum()):,}",
        f"- **max |next_interval_dia_delta_mm| after quarantine:** {max_abs_label:.2f} mm",
        "",
        "## Why",
        "",
        "Label spec 1.0.0 retained physically-impossible label endpoints (bronze wsmDia1 values of 0 and >1e6 mm), producing |delta| labels up to ~1090 mm. These carry ~30% of total regression MSE and poison the training target distribution. Label spec 1.0.1 adds a deterministic quarantine rule (patch bump, per Continuous Evolution Guide section 2). See `models/experiments/v1.2/sentinel_audit_findings.md`.",
        "",
        "## Provenance",
        "",
        f"- `parent_dataset_version`: {PARENT_VERSION}",
        f"- `feature_store_version`: {out_manifest['feature_store_version']}",
        f"- `feature_spec_version`: {out_manifest['feature_spec_version']}",
        f"- `label_spec_version`: {label_spec['label_specification_version']}",
        f"- Generated: {out_manifest['generated_at_utc']}",
    ]
    (V1_2_DIR / "dataset_card.md").write_text("\n".join(card) + "\n", encoding="utf-8")

    print(f"v1.2 dataset written: {V1_2_DIR}  (quarantined {quarantined:,} rows)")
    return {"dataset": V1_2_DIR / "model_dataset_v1.2.parquet",
            "manifest": V1_2_DIR / "model_dataset_manifest_v1.2.json",
            "card": V1_2_DIR / "dataset_card.md"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, path in build_model_dataset_v1_2(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
