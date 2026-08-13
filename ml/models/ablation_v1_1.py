"""V1.1 ablation — per-group contribution of measured geometry vs physics features.

Runs HGB (best stable model) on four feature-set variants on the TEST split only:
  - v1_0          : v1.0 features
  - +geom         : v1.0 + geom_* (raw measured geometry at interval end)
  - +phys         : v1.0 + phys_* (engineered physics state)
  - +all          : v1.0 + geom_* + phys_*

Purpose: quantify how much of the V1.1 gain comes from simply exposing the
absolute measured geometry vs from the engineered physics features.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402

DATASET_V1_0 = PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_v1.0.parquet"
DATASET_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
MANIFEST_V1_0 = PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_manifest_v1.0.json"
MANIFEST_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_manifest_v1.1.json"
OUT_DIR = PROJECT_ROOT / "models" / "experiments" / "v1.1" / "ablation"
RANDOM_STATE = 42

TASKS = [
    ("regression", "next_interval_dia_delta_mm"),
    ("binary", "next_interval_large_loss_flag"),
    ("binary", "next_interval_turning_flag"),
]


def _feature_sets() -> dict[str, list[str]]:
    m10 = json.loads(MANIFEST_V1_0.read_text(encoding="utf-8"))
    m11 = json.loads(MANIFEST_V1_1.read_text(encoding="utf-8"))
    base = [c for c, r in m10["column_roles"].items() if r == "feature"]
    all11 = [c for c, r in m11["column_roles"].items() if r == "feature"]
    geom = [c for c in all11 if c.startswith("geom_")]
    phys = [c for c in all11 if c.startswith("phys_")]
    return {
        "v1_0": base,
        "plus_geom": base + geom,
        "plus_phys": base + phys,
        "plus_all": base + geom + phys,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ds10 = pd.read_parquet(DATASET_V1_0)
    ds11 = pd.read_parquet(DATASET_V1_1)
    # v1.1 superset of v1.0 rows; align by operational_exposure_id
    ds = ds11.set_index("operational_exposure_id")
    ds = ds.loc[ds10.set_index("operational_exposure_id").index].reset_index()

    train = ds[ds["split"] == "train"]
    test = ds[ds["split"] == "test"]
    feature_sets = _feature_sets()

    rows = []
    for task, label in TASKS:
        for variant, feats in feature_sets.items():
            if task == "regression":
                model = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
                model.fit(train[feats], train[label])
                y_pred = model.predict(test[feats])
                metrics = evaluate.regression_metrics(test[label], y_pred)
                metrics = {"mae": metrics["mae"], "rmse": metrics["rmse"], "spearman": metrics["spearman"]}
            else:
                model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
                model.fit(train[feats], train[label])
                y_prob = model.predict_proba(test[feats])[:, 1]
                metrics = evaluate.binary_metrics(test[label], y_prob, k=min(2000, len(test)))
                metrics = {"pr_auc": metrics["pr_auc"], "roc_auc": metrics["roc_auc"]}
            rows.append({"task": task, "label": label, "variant": variant, "n_features": len(feats), **metrics})

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "ablation.csv", index=False)
    print(df.pivot(index=["task", "label"], columns="variant").round(4).to_string())


if __name__ == "__main__":
    main()
