"""Phase 3A + 3B baselines under the identical grouped temporal split.

Phase 3A (can we beat stupid?): Dummy mean/median (regression), majority/prior (binary),
median-time (survival).
Phase 3B (real models): Linear / ElasticNet / HistGradientBoosting (sklearn stand-in for
LightGBM/CatBoost/XGBoost — installable later without changing the harness).

Every (task, label, model) is a separate experiment_XXXX run in the registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, LinearRegression, LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATA_DIR = PROJECT_ROOT / "model_datasets" / "v1.0"
DATASET_PATH = DATA_DIR / "model_dataset_v1.0.parquet"
MANIFEST_PATH = DATA_DIR / "model_dataset_manifest_v1.0.json"
EVAL_SPEC_PATH = PROJECT_ROOT / "configs" / "evaluation_spec.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v1.0"
RANDOM_STATE = 42

TASKS = ["regression", "binary", "survival"]

REGRESSION_LABEL = "next_interval_dia_delta_mm"
BINARY_LABELS = ["next_interval_turning_flag", "next_interval_large_loss_flag"]
SURVIVAL_LABEL = "time_to_next_turning_days"
SURVIVAL_CENSOR = "censored_flag"


def _load() -> tuple[pd.DataFrame, dict]:
    dataset = pd.read_parquet(DATASET_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return dataset, manifest


def _feature_importance(model, x_columns: list[str]) -> dict:
    if hasattr(model, "steps"):
        model = model.steps[-1][1]
    try:
        importances = getattr(model, "feature_importances_", None)
        if importances is not None:
            rank = pd.Series(importances, index=x_columns).sort_values(ascending=False)
            return {"kind": "importance", "top_30": rank.head(30).to_dict()}
    except Exception:
        pass
    try:
        coefs = getattr(model, "coef_", None)
        if coefs is not None:
            coef = coefs[0] if getattr(model, "classes_", None) is not None and len(getattr(model, "classes_", [])) == 2 else coefs
            rank = pd.Series(np.asarray(coef).ravel(), index=x_columns).sort_values(key=np.abs, ascending=False)
            return {"kind": "coefficients", "top_30": rank.head(30).to_dict()}
    except Exception:
        pass
    return {"kind": "unavailable"}


def _run_regression(dataset: pd.DataFrame, manifest: dict) -> list[dict]:
    x_cols = manifest["column_roles"]
    features = [c for c, r in x_cols.items() if r == "feature"]
    train = dataset[dataset["split"] == "train"]
    rows = []
    for split_name in ("val", "test"):
        eval_set = dataset[dataset["split"] == split_name]
        for name, estimator in [
            ("dummy_mean", DummyRegressor(strategy="mean")),
            ("dummy_median", DummyRegressor(strategy="median")),
            ("linear", LinearRegression()),
            ("elastic_net", make_pipeline(StandardScaler(), ElasticNet(max_iter=10000, random_state=RANDOM_STATE))),
            ("hist_gradient_boosting", HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
        ]:
            estimator.fit(train[features], train[REGRESSION_LABEL])
            y_pred = estimator.predict(eval_set[features])
            metrics = evaluate.regression_metrics(eval_set[REGRESSION_LABEL], y_pred)
            config = {"phase": "3A" if name.startswith("dummy") else "3B", "task": "regression", "label": REGRESSION_LABEL, "model": name, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "random_state": RANDOM_STATE}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "regression", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features))
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "y_true": eval_set[REGRESSION_LABEL], "y_pred": y_pred,
            }))
            write_manifest(run_dir, {"dataset_version": manifest["dataset_version"], "feature_store_version": manifest["feature_store_version"], "feature_spec_version": manifest["feature_spec_version"], "label_spec_version": manifest["label_spec_version"]})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "regression", "label": REGRESSION_LABEL, "model": name, "phase": config["phase"], "split": split_name, **metrics})
    return rows


def _run_binary(dataset: pd.DataFrame, manifest: dict, label: str) -> list[dict]:
    x_cols = manifest["column_roles"]
    features = [c for c, r in x_cols.items() if r == "feature"]
    train = dataset[dataset["split"] == "train"]
    rows = []
    for split_name in ("val", "test"):
        eval_set = dataset[dataset["split"] == split_name]
        for name, estimator in [
            ("dummy_majority", DummyClassifier(strategy="most_frequent")),
            ("dummy_prior", DummyClassifier(strategy="prior")),
            ("logistic", make_pipeline(StandardScaler(), LogisticRegression(max_iter=10000, random_state=RANDOM_STATE))),
            ("hist_gradient_boosting", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
        ]:
            estimator.fit(train[features], train[label])
            y_prob = estimator.predict_proba(eval_set[features])[:, 1]
            metrics = evaluate.binary_metrics(eval_set[label], y_prob, k=min(2000, len(eval_set)))
            config = {"phase": "3A" if name.startswith("dummy") else "3B", "task": "binary", "label": label, "model": name, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "random_state": RANDOM_STATE}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "binary", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features))
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "y_true": eval_set[label], "y_prob": y_prob,
            }))
            write_manifest(run_dir, {"dataset_version": manifest["dataset_version"], "feature_store_version": manifest["feature_store_version"], "feature_spec_version": manifest["feature_spec_version"], "label_spec_version": manifest["label_spec_version"]})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "binary", "label": label, "model": name, "phase": config["phase"], "split": split_name, **metrics})
    return rows


def _run_survival(dataset: pd.DataFrame, manifest: dict) -> list[dict]:
    x_cols = manifest["column_roles"]
    features = [c for c, r in x_cols.items() if r == "feature"]
    train = dataset[dataset["split"] == "train"]
    rows = []
    for split_name in ("val", "test"):
        eval_set = dataset[dataset["split"] == split_name]
        time_eval = eval_set[SURVIVAL_LABEL]
        censor_eval = eval_set[SURVIVAL_CENSOR].astype(int)
        event_eval = (1 - censor_eval).astype(int)
        observed_train = train[~train[SURVIVAL_CENSOR]]
        median_time = float(observed_train[SURVIVAL_LABEL].median())

        estimators = [
            ("dummy_median_time", None),
            ("hist_gradient_boosting_observed_only", HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
        ]
        for name, estimator in estimators:
            if estimator is None:
                risk = np.full(len(eval_set), -median_time)
            else:
                estimator.fit(observed_train[features], observed_train[SURVIVAL_LABEL])
                risk = -estimator.predict(eval_set[features])
            metrics = evaluate.survival_metrics(time_eval, event_eval, risk)
            config = {"phase": "3A" if name == "dummy_median_time" else "3B", "task": "survival", "label": SURVIVAL_LABEL, "model": name, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "risk_definition": "-predicted_time", "note": "GBM trained on observed (uncensored) rows only; proper survival models (Cox/survival forests) are future work"}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "survival", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features) if estimator is not None else {"kind": "unavailable"})
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "time_to_event": time_eval, "censored": censor_eval, "risk_score": risk,
            }))
            write_manifest(run_dir, {"dataset_version": manifest["dataset_version"], "feature_store_version": manifest["feature_store_version"], "feature_spec_version": manifest["feature_spec_version"], "label_spec_version": manifest["label_spec_version"]})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "survival", "label": SURVIVAL_LABEL, "model": name, "phase": config["phase"], "split": split_name, **metrics})
    return rows


def main(seed: int = RANDOM_STATE) -> None:
    dataset, manifest = _load()
    rows = []
    rows += _run_regression(dataset, manifest)
    for label in BINARY_LABELS:
        rows += _run_binary(dataset, manifest, label)
    rows += _run_survival(dataset, manifest)

    comparison = pd.DataFrame(rows).sort_values(["task", "label", "model", "split"])
    comparison.to_csv(EXPERIMENTS_ROOT / "comparison.csv", index=False)

    # Summary markdown (per task/label, test split).
    summary = ["# Baseline comparison (v1.0)", ""]
    for task in TASKS:
        summary.append(f"## {task}")
        summary.append("")
        summary.append("| model | label | split | metric | value |")
        summary.append("| --- | --- | --- | --- | --- |")
        for _, r in comparison[comparison["task"] == task].sort_values("model").iterrows():
            metric_key = {"regression": "rmse", "binary": "pr_auc", "survival": "c_index"}[task]
            value = r.get(metric_key)
            summary.append(f"| {r['model']} | {r['label']} | {r['split']} | {metric_key} | {value} |")
        summary.append("")
    (EXPERIMENTS_ROOT / "comparison_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"ran {len(rows)} experiment evaluations -> {EXPERIMENTS_ROOT}")
    print(comparison.groupby(["task", "label", "model"])[["rmse", "pr_auc", "c_index"]].mean().round(4).to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=RANDOM_STATE)
    args = parser.parse_args()
    main(seed=args.seed)
