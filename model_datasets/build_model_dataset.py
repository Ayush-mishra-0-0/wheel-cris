"""Model Dataset builder v1.0.

Reads: Feature Store v1.0 (via the Training Eligibility Filter manifest) + raw
WheelSetMeasurements (labels). Emits a versioned, model-ready dataset:

  - X      : eligible columns, encoded per the eligibility manifest
             (one-hot / frequency / ordinal / numeric), encoders fit on TRAIN
             only to avoid leakage
  - y      : the four label families from configs/label_specification.json
  - meta   : identity + grouping keys for splits (kept, never used as features)
  - split  : grouped temporal split (train 70 / val 15 / test 15) keyed by
             equipment MEDIAN interval-end, so a wheelset never spans splits

Every row knows its provenance:
  dataset_version, feature_store_version, feature_spec_version, label_spec_version.

No overwrite / no silent regeneration: outputs are written to a versioned
directory and refuse to overwrite an existing dataset unless --force is passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from silver_gold.transform import BRONZE_DIR, _sha256  # noqa: E402

CONFIG_DIR = PROJECT_ROOT / "configs"
MODEL_DATASET_DIR = PROJECT_ROOT / "model_datasets"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"
MEASUREMENTS_PATH = BRONZE_DIR / "wheel_measurements.parquet"
ELIGIBILITY_MANIFEST = MODEL_DATASET_DIR / "training_eligibility_manifest_v1.json"

DATASET_VERSION = "v1.0"
FEATURE_STORE_VERSION = "1.0.0"
FEATURE_SPEC_VERSION = "1.0.0"
LABEL_SPEC_VERSION = "1.0.0"

SPLIT = {"train": 0.70, "val": 0.15, "test": 0.15}


def _fingerprint(*items: str) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.encode("utf-8"))
    return digest.hexdigest()[:16]


def _days_since(events: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """Days from `ends` to the next `events` entry; NaN where no event is present (NaT-safe)."""
    delta = events - ends
    days = delta.astype("timedelta64[D]").astype(float)
    return np.where(pd.isna(events) | pd.isna(ends), np.nan, days)


def _load_measurement_frame() -> pd.DataFrame:
    """Per-measurement geometry + turning needed for forward labels, keyed by equipment."""
    cols = ["wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmDia1", "wsmRoot1", "wsmturning1"]
    frame = pd.read_parquet(MEASUREMENTS_PATH)[cols].copy()
    frame["wsmId"] = pd.to_numeric(frame["wsmId"], errors="coerce").astype("Int64")
    frame["wsmEquipmentId"] = pd.to_numeric(frame["wsmEquipmentId"], errors="coerce").astype("Int64")
    frame["wsmturning1"] = pd.to_numeric(frame["wsmturning1"], errors="coerce").astype("Int64")
    frame["wsmDia1"] = pd.to_numeric(frame["wsmDia1"], errors="coerce")
    frame["wsmRoot1"] = pd.to_numeric(frame["wsmRoot1"], errors="coerce")
    frame["wsmUpdatedOn"] = pd.to_datetime(frame["wsmUpdatedOn"], errors="coerce")
    return frame


def _build_labels(rows: pd.DataFrame, measurements: pd.DataFrame) -> pd.DataFrame:
    """Forward labels: properties of the NEXT measurement per wheelset after the row's interval end."""
    label_spec = json.loads((CONFIG_DIR / "label_specification.json").read_text(encoding="utf-8"))
    # Sort for the forward sweep but KEEP the original index so the resulting
    # labels align back to the caller's rows by index label (no positional drift).
    rows = rows.sort_values("interval_end_timestamp")

    next_meas_id = np.full(len(rows), pd.NA, dtype=object)
    next_time = np.full(len(rows), np.datetime64("NaT"), dtype="datetime64[ns]")
    next_dia1 = np.full(len(rows), np.nan)
    next_root1 = np.full(len(rows), np.nan)
    next_turning = np.full(len(rows), pd.NA, dtype=object)
    next_turning_time = np.full(len(rows), np.datetime64("NaT"), dtype="datetime64[ns]")

    clean = measurements.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).sort_values("wsmUpdatedOn")
    turning = clean[clean["wsmturning1"] == 1]

    def index_times(frame: pd.DataFrame) -> dict[int, np.ndarray]:
        return {eid: group["wsmUpdatedOn"].to_numpy(dtype="datetime64[ns]") for eid, group in frame.groupby("wsmEquipmentId", sort=False)}

    meas_times = index_times(clean)
    turning_times = index_times(turning)
    meas_dia = {eid: group["wsmDia1"].to_numpy() for eid, group in clean.groupby("wsmEquipmentId", sort=False)}
    meas_root = {eid: group["wsmRoot1"].to_numpy() for eid, group in clean.groupby("wsmEquipmentId", sort=False)}
    meas_turn = {eid: group["wsmturning1"].to_numpy() for eid, group in clean.groupby("wsmEquipmentId", sort=False)}
    meas_id = {eid: group["wsmId"].to_numpy() for eid, group in clean.groupby("wsmEquipmentId", sort=False)}

    ends = rows["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
    equipment = rows["wheelset_equipment_id"].to_numpy()
    for eid, group in rows.groupby("wheelset_equipment_id", sort=False):
        times = meas_times.get(eid)
        if times is None or len(times) == 0:
            continue
        rows_idx = group.index.to_numpy()
        pos = np.searchsorted(times, ends[rows_idx], side="right")
        nxt = pos < len(times)
        if nxt.any():
            hit = rows_idx[nxt]
            np_idx = pos[nxt]
            next_meas_id[hit] = meas_id[eid][np_idx]
            next_time[hit] = times[np_idx]
            next_dia1[hit] = meas_dia[eid][np_idx]
            next_root1[hit] = meas_root[eid][np_idx]
            next_turning[hit] = meas_turn[eid][np_idx]
        t_times = turning_times.get(eid)
        if t_times is not None and len(t_times) > 0:
            t_pos = np.searchsorted(t_times, ends[rows_idx], side="right")
            t_hit = t_pos < len(t_times)
            if t_hit.any():
                next_turning_time[rows_idx[t_hit]] = t_times[t_pos[t_hit]]

    labels = pd.DataFrame({
        "next_interval_end_measurement_id": pd.Series(next_meas_id, dtype="Int64"),
        "next_interval_end_timestamp": next_time,
        "next_interval_dia_delta_mm": next_dia1 - rows["interval_end_dia1"].to_numpy(),
        "next_interval_root_delta_mm": next_root1 - rows["interval_end_root1"].to_numpy(),
        "next_interval_turning_flag": pd.Series(next_turning, dtype="Int64"),
        "time_to_next_turning_days": _days_since(next_turning_time, ends),
    })
    labels.index = rows.index  # arrays are in sorted order; index maps back to the original rows
    labels["next_interval_large_loss_flag"] = pd.Series(pd.NA, dtype="Int64")
    has_next = ~pd.isna(next_time)
    large = (labels["next_interval_dia_delta_mm"] <= -2.0) | (labels["next_interval_root_delta_mm"] <= -1.0)
    labels.loc[has_next, "next_interval_large_loss_flag"] = large[has_next].astype("Int64")
    # Missing turning flag at a present next measurement -> record as no turning.
    labels.loc[has_next, "next_interval_turning_flag"] = labels.loc[has_next, "next_interval_turning_flag"].fillna(0)
    labels["censored_flag"] = has_next & pd.isna(next_turning_time)
    labels["next_interval_available"] = has_next
    return labels


def _assign_grouped_temporal_split(rows: pd.DataFrame) -> pd.Series:
    """Grouped temporal split keyed by equipment MEDIAN interval-end (no wheelset spans splits)."""
    medians = rows.groupby("wheelset_equipment_id", sort=False)["interval_end_timestamp"].transform("median")
    n = len(rows)
    bounds = np.cumsum([0.0, SPLIT["train"], SPLIT["val"], SPLIT["test"]])

    def assign(rank: float) -> str:
        frac = (rank - 1.0) / n
        if frac < bounds[1]:
            return "train"
        if frac < bounds[2]:
            return "val"
        return "test"

    return medians.rank(method="min").map(assign)


def _encode_x(rows: pd.DataFrame, manifest: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Encode eligible columns. Numeric median + frequency/one-hot/ordinal encoders are fit on TRAIN only."""
    eligible = manifest["eligible_columns"]
    policy = manifest["encoding_policy"]
    train_mask = rows["split"] == "train"
    train = rows[train_mask]

    parts: list[pd.DataFrame] = []
    encoding_summary: dict[str, dict] = {}

    for column in eligible:
        policy_kind = policy[column]
        if policy_kind == "numeric":
            median = float(train[column].median())
            encoded = pd.DataFrame({column: rows[column].fillna(median)})
            encoding_summary[column] = {"policy": "numeric", "train_median_impute": median, "missing_fill": "median_on_train"}
        elif policy_kind == "ordinal_binary":
            levels = sorted(train[column].dropna().unique())
            value_map = {level: i for i, level in enumerate(levels)}
            encoded = pd.DataFrame({column: rows[column].map(value_map).fillna(-1)})  # -1 = missing sentinel
            encoding_summary[column] = {"policy": "ordinal_binary", "train_levels": {str(k): v for k, v in value_map.items()}, "missing_sentinel": -1}
        elif policy_kind == "one_hot":
            levels = sorted(train[column].dropna().astype(str).unique())
            encoded = pd.DataFrame(index=rows.index)
            for level in levels:
                col = f"{column}__{level}"
                encoded[col] = (rows[column].astype("string").fillna("__NA__") == level).astype(int)
            encoding_summary[column] = {"policy": "one_hot", "train_levels": levels, "na_bucket": "__NA__"}
        elif policy_kind == "frequency":
            freqs = train[column].fillna("__NA__").astype(str).value_counts(normalize=True)
            encoded = pd.DataFrame({f"{column}__freq": rows[column].fillna("__NA__").astype(str).map(freqs).fillna(0.0)})
            encoding_summary[column] = {"policy": "frequency", "train_unseen_encoding": 0.0}
        else:
            raise ValueError(f"Unknown encoding policy {policy_kind} for {column}")
        parts.append(encoded)

    X = pd.concat(parts, axis=1)
    return X, pd.DataFrame({"column": list(policy), "encoding_summary": [encoding_summary[c] for c in policy]})


def _write_dataset_card(dataset: pd.DataFrame, dataset_manifest: dict, out_dir: Path) -> Path:
    """Self-describing markdown card for one dataset version."""
    x_cols = [c for c, role in dataset_manifest["column_roles"].items() if role == "feature"]
    label_cols = [c for c, role in dataset_manifest["column_roles"].items() if role == "label"]
    x_na = dataset[x_cols].isna().sum().sum()
    card = [
        f"# Dataset Card — model dataset {dataset_manifest['dataset_version']}",
        "",
        f"- **Rows (supervised):** {len(dataset):,}",
        f"- **Features (X):** {len(x_cols)} (NA cells in X: {int(x_na):,})",
        f"- **Labels:** {len(label_cols)} ({', '.join(label_cols)})",
        f"- **Wheelsets:** {dataset['wheelset_equipment_id'].nunique():,}",
        f"- **Locomotives:** {dataset['locomotive_id'].nunique():,}",
        f"- **Date range:** {dataset['interval_end_timestamp'].min():%Y-%m-%d} → {dataset['interval_end_timestamp'].max():%Y-%m-%d}",
        f"- **Split rows:** train={int((dataset['split']=='train').sum()):,} · val={int((dataset['split']=='val').sum()):,} · test={int((dataset['split']=='test').sum()):,}",
        f"- **Grouped split:** by median interval-end per wheelset (no wheelset spans splits)",
        "",
        "## Provenance",
        "",
        f"- `feature_store_version`: {dataset_manifest['feature_store_version']}",
        f"- `feature_spec_version`: {dataset_manifest['feature_spec_version']}",
        f"- `label_spec_version`: {dataset_manifest['label_spec_version']}",
        f"- `fingerprint`: `{dataset_manifest['fingerprint']}`",
        f"- Generated: {dataset_manifest['generated_at_utc']}",
        "",
        "## Missingness summary (X features)",
        "",
        "| Column | NA rows | NA % |",
        "| --- | ---: | ---: |",
    ]
    for col in x_cols:
        n = int(dataset[col].isna().sum())
        card.append(f"| {col} | {n:,} | {n/len(dataset)*100:.2f}% |")
    card += [
        "",
        "## Label prevalence",
        "",
        "| Label | prevalence / mean |",
        "| --- | --- |",
    ]
    for col in label_cols:
        s = dataset[col]
        card.append(f"| {col} | {s.mean():.4f} |")
    card += [
        "",
        "## Known limitations",
        "",
        "1. Labels are candidate (not approved): see `configs/label_specification.json` `validation_status`.",
        "2. `next_interval_turning_flag` is imbalanced (~1.8% positive); flag may undercount ~0.6% of pairs (Q2).",
        "3. `time_to_next_turning_days` is 90% right-censored; evaluate with survival metrics (C-index), not plain RMSE.",
        "4. `next_interval_large_loss_flag` uses heuristic thresholds (-2.0 mm dia / -1.0 mm root).",
        "5. Encoders and imputers were fit on TRAIN only; NA sentinels: ordinal_binary=-1, one_hot/frequency=\"__NA__\" bucket.",
        "6. `next_interval_dia_delta_mm` / `next_interval_root_delta_mm` contain raw sentinel outliers (min/max ~±1090 mm / ±2047 mm) from source measurements outside quarantine [600,1300] mm dia; regression RMSE will be inflated until a quarantined label version (label_spec >= 1.1).",
    ]
    path = out_dir / "dataset_card.md"
    path.write_text("\n".join(card) + "\n", encoding="utf-8")
    return path


def build_model_dataset(force: bool = False) -> dict[str, Path]:
    if not ELIGIBILITY_MANIFEST.exists():
        raise FileNotFoundError("Run model_datasets/training_eligibility.py first")
    manifest = json.loads(ELIGIBILITY_MANIFEST.read_text(encoding="utf-8"))
    label_spec = json.loads((CONFIG_DIR / "label_specification.json").read_text(encoding="utf-8"))
    spec = json.loads((CONFIG_DIR / "engineering_feature_specification_v1.json").read_text(encoding="utf-8"))

    store = pd.read_parquet(STORE_PATH)
    measurements = _load_measurement_frame()

    # Endpoint geometry for forward-delta labels (this interval's end = next interval's start).
    end_wm = measurements[["wsmId", "wsmDia1", "wsmRoot1"]].copy()
    end_wm["wsmId"] = end_wm["wsmId"].astype("Int64")
    rows = store.merge(
        end_wm.rename(columns={"wsmDia1": "interval_end_dia1", "wsmRoot1": "interval_end_root1"}),
        left_on="interval_end_measurement_id", right_on="wsmId", how="left", validate="one_to_one",
    )
    rows = rows.merge(end_wm.rename(columns={"wsmDia1": "interval_start_dia1", "wsmRoot1": "interval_start_root1"}), left_on="interval_start_measurement_id", right_on="wsmId", how="left", validate="one_to_one")

    labels = _build_labels(rows, measurements)
    rows = pd.concat([rows, labels], axis=1)
    rows["split"] = _assign_grouped_temporal_split(rows)
    X, encoding_meta = _encode_x(rows, manifest)

    # Supervised rows only where the next interval exists (all labels available).
    supervised = rows[rows["next_interval_available"]].copy()
    X_supervised = X.loc[supervised.index]
    dropped_no_next = int((~rows["next_interval_available"]).sum())

    # Final dataset: start from supervised rows, drop raw categorical sources and
    # label-helper columns, then apply encoded X (numeric/ordinal overwrite in
    # place; one-hot/frequency add new columns).
    raw_categoricals = [c for c in manifest["eligible_columns"] if manifest["encoding_policy"].get(c) in ("one_hot", "frequency")]
    helper_columns = ["wsmId_x", "wsmId_y", "interval_end_dia1", "interval_end_root1", "interval_start_dia1", "interval_start_root1"]
    dataset = supervised.drop(columns=raw_categoricals + helper_columns, errors="ignore")
    for column in X_supervised.columns:
        dataset[column] = X_supervised[column].to_numpy()

    identity = ["operational_exposure_id", "interval_start_measurement_id", "interval_end_measurement_id", "wheelset_equipment_id", "locomotive_id", "locomotive_number", "interval_start_timestamp", "interval_end_timestamp", "timeline_quality_tier", "LocoType", "split", "next_interval_available", "next_interval_end_measurement_id", "next_interval_end_timestamp"]
    y_columns = ["next_interval_dia_delta_mm", "next_interval_root_delta_mm", "next_interval_turning_flag", "next_interval_large_loss_flag", "time_to_next_turning_days", "censored_flag"]
    x_columns = list(X_supervised.columns)
    eda_context = ["home_shed", "defect_zone", "defect_division", "wheel_schedule_id"]  # raw categoricals, not model inputs
    keep = set(identity) | set(y_columns) | set(x_columns) | set(eda_context)
    dataset = dataset.drop(columns=[c for c in dataset.columns if c not in keep])
    column_roles = {c: "meta" for c in identity}
    for c in y_columns:
        column_roles[c] = "label"
    for c in x_columns:
        column_roles[c] = "feature"
    for c in eda_context:
        column_roles[c] = "eda_context"

    out_dir = MODEL_DATASET_DIR / DATASET_VERSION
    if out_dir.exists() and not force:
        raise FileExistsError(f"{out_dir} already exists; use --force to regenerate (never regenerate silently)")

    dataset_manifest = {
        "dataset_version": DATASET_VERSION,
        "feature_store_version": FEATURE_STORE_VERSION,
        "feature_spec_version": spec.get("specification_version"),
        "label_spec_version": label_spec.get("label_specification_version"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {
            "feature_store": _sha256(STORE_PATH),
            "wheel_measurements": _sha256(MEASUREMENTS_PATH),
            "eligibility_manifest": _sha256(ELIGIBILITY_MANIFEST),
            "label_spec": _sha256(CONFIG_DIR / "label_specification.json"),
            "feature_spec": _sha256(CONFIG_DIR / "engineering_feature_specification_v1.json"),
        },
        "fingerprint": _fingerprint(str(_sha256(STORE_PATH)), str(_sha256(MEASUREMENTS_PATH)), DATASET_VERSION),
        "rows": {"total": int(len(rows)), "supervised": int(len(supervised)), "dropped_no_next_interval": dropped_no_next},
        "split_rows": {name: int((supervised["split"] == name).sum()) for name in SPLIT},
        "labels": {label["label_id"]: {"family": label["family"], "validation_status": label["validation_status"]} for label in label_spec["labels"]},
        "eligible_columns": manifest["eligible_columns"],
        "x_columns": x_columns,
        "encoding": encoding_meta.to_dict(orient="records"),
        "column_roles": column_roles,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(out_dir / "model_dataset_v1.0.parquet", index=False)
    (out_dir / "model_dataset_manifest_v1.0.json").write_text(json.dumps(dataset_manifest, indent=2) + "\n", encoding="utf-8")
    for name in SPLIT:
        dataset[dataset["split"] == name].to_parquet(out_dir / f"{name}_v1.0.parquet", index=False)
    card_path = _write_dataset_card(dataset, dataset_manifest, out_dir)
    return {"dataset": out_dir / "model_dataset_v1.0.parquet", "manifest": out_dir / "model_dataset_manifest_v1.0.json", "dataset_card": card_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="allow regeneration of an existing dataset version")
    args = parser.parse_args()
    for name, path in build_model_dataset(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
