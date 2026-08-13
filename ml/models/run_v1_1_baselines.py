"""V1.1 model comparison — v1.0 features vs v1.1 (physics + measured geometry).

Runs the same 4-5 models on the identical grouped temporal split with two feature
sets:
  - baseline   : v1.0 X features only
  - v1_1       : v1.0 + physics (phys_*) + measured geometry (geom_*)

Models per task:
  - regression : dummy_mean, linear, elastic_net, hist_gradient_boosting, random_forest
  - binary     : dummy_prior, logistic, hist_gradient_boosting, random_forest
  - survival   : dummy_median_time, hist_gradient_boosting_observed_only, random_forest_observed_only

Every (task, label, feature_set, model) becomes an experiment_XXXX run in the
registry (same experiment_registry as v1.0), so results are directly comparable.
Outputs: models/experiments/v1.1/comparison.csv + comparison_summary.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import ElasticNet, LinearRegression, LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_V1_0 = PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_v1.0.parquet"
DATASET_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
MANIFEST_V1_0 = PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_manifest_v1.0.json"
MANIFEST_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_manifest_v1.1.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v1.1"
RANDOM_STATE = 42

REGRESSION_LABEL = "next_interval_dia_delta_mm"
BINARY_LABELS = ["next_interval_turning_flag", "next_interval_large_loss_flag"]
SURVIVAL_LABEL = "time_to_next_turning_days"
SURVIVAL_CENSOR = "censored_flag"


def _feature_columns(dataset_version: str, manifest: dict) -> list[str]:
    roles = manifest["column_roles"]
    base = [c for c, r in roles.items() if r == "feature"]
    if dataset_version == "v1.0":
        return base
    if dataset_version == "v1.1":
        return base
    raise ValueError(dataset_version)


def _feature_importance(model, x_columns: list[str], eval_set: pd.DataFrame = None, label: str = None, kind: str = "regression") -> dict:
    if hasattr(model, "steps"):
        model = model.steps[-1][1]
    try:
        importances = getattr(model, "feature_importances_", None)
        if importances is not None and np.asarray(importances).size == len(x_columns):
            rank = pd.Series(np.asarray(importances).ravel(), index=x_columns).sort_values(ascending=False)
            return {"kind": "importance", "top_30": rank.head(30).to_dict()}
    except Exception:
        pass
    # Permutation importance fallback (needs the eval set; sklearn 1.9 HGB no longer
    # exposes feature_importances_, and linear/logistic have no native importance).
    if eval_set is not None and label is not None:
        try:
            from sklearn.inspection import permutation_importance
            X_eval = eval_set[x_columns]
            scorer = "neg_mean_squared_error" if kind == "regression" else "roc_auc"
            perm = permutation_importance(model, X_eval, eval_set[label], n_repeats=4, random_state=42, scoring=scorer, n_jobs=-1)
            rank = pd.Series(perm.importances_mean, index=x_columns).sort_values(ascending=False)
            return {"kind": "permutation_importance", "scorer": scorer, "top_30": rank.head(30).to_dict()}
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


def _run_regression(dataset: pd.DataFrame, manifest: dict, version: str) -> list[dict]:
    features = _feature_columns(version, manifest)
    train = dataset[dataset["split"] == "train"]
    rows = []
    for split_name in ("val", "test"):
        eval_set = dataset[dataset["split"] == split_name]
        for name, estimator in [
            ("dummy_mean", DummyRegressor(strategy="mean")),
            ("linear", LinearRegression()),
            ("elastic_net", make_pipeline(StandardScaler(), ElasticNet(max_iter=10000, random_state=RANDOM_STATE))),
            ("hist_gradient_boosting", HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
            ("random_forest", RandomForestRegressor(n_estimators=150, max_depth=18, min_samples_leaf=25, n_jobs=-1, random_state=RANDOM_STATE)),
        ]:
            estimator.fit(train[features], train[REGRESSION_LABEL])
            y_pred = estimator.predict(eval_set[features])
            metrics = evaluate.regression_metrics(eval_set[REGRESSION_LABEL], y_pred)
            config = {"phase": "v1.1", "task": "regression", "label": REGRESSION_LABEL, "model": name, "feature_set": version, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "random_state": RANDOM_STATE}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "regression", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features, eval_set, REGRESSION_LABEL, "regression"))
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "y_true": eval_set[REGRESSION_LABEL], "y_pred": y_pred,
            }))
            write_manifest(run_dir, {"dataset_version": f"v1.1-{version}-features", "feature_store_version": "1.0.0", "feature_spec_version": "1.0.0", "label_spec_version": "1.0.0"})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "regression", "label": REGRESSION_LABEL, "model": name, "feature_set": version, "split": split_name, **metrics})
    return rows


def _run_binary(dataset: pd.DataFrame, manifest: dict, label: str, version: str) -> list[dict]:
    features = _feature_columns(version, manifest)
    train = dataset[dataset["split"] == "train"]
    rows = []
    for split_name in ("val", "test"):
        eval_set = dataset[dataset["split"] == split_name]
        for name, estimator in [
            ("dummy_prior", DummyClassifier(strategy="prior")),
            ("logistic", make_pipeline(StandardScaler(), LogisticRegression(max_iter=10000, random_state=RANDOM_STATE))),
            ("hist_gradient_boosting", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
            ("random_forest", RandomForestClassifier(n_estimators=150, max_depth=18, min_samples_leaf=25, n_jobs=-1, random_state=RANDOM_STATE)),
        ]:
            estimator.fit(train[features], train[label])
            y_prob = estimator.predict_proba(eval_set[features])[:, 1]
            metrics = evaluate.binary_metrics(eval_set[label], y_prob, k=min(2000, len(eval_set)))
            config = {"phase": "v1.1", "task": "binary", "label": label, "model": name, "feature_set": version, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "random_state": RANDOM_STATE}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "binary", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features, eval_set, label, "binary"))
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "y_true": eval_set[label], "y_prob": y_prob,
            }))
            write_manifest(run_dir, {"dataset_version": f"v1.1-{version}-features", "feature_store_version": "1.0.0", "feature_spec_version": "1.0.0", "label_spec_version": "1.0.0"})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "binary", "label": label, "model": name, "feature_set": version, "split": split_name, **metrics})
    return rows


def _run_survival(dataset: pd.DataFrame, manifest: dict, version: str) -> list[dict]:
    features = _feature_columns(version, manifest)
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
            ("random_forest_observed_only", RandomForestRegressor(n_estimators=150, max_depth=18, min_samples_leaf=25, n_jobs=-1, random_state=RANDOM_STATE)),
        ]
        for name, estimator in estimators:
            if estimator is None:
                risk = np.full(len(eval_set), -median_time)
            else:
                estimator.fit(observed_train[features], observed_train[SURVIVAL_LABEL])
                risk = -estimator.predict(eval_set[features])
            metrics = evaluate.survival_metrics(time_eval, event_eval, risk)
            config = {"phase": "v1.1", "task": "survival", "label": SURVIVAL_LABEL, "model": name, "feature_set": version, "split_contract": "grouped temporal train/val/test by wheelset median interval-end", "risk_definition": "-predicted_time", "note": "GBM/RF trained on observed (uncensored) rows only"}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "survival", config)
            write_metrics(run_dir, {split_name: metrics})
            write_feature_importance(run_dir, _feature_importance(estimator, features, eval_set, SURVIVAL_LABEL, "regression") if estimator is not None else {"kind": "unavailable"})
            write_model(run_dir, estimator)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": eval_set["operational_exposure_id"], "split": split_name, "time_to_event": time_eval, "censored": censor_eval, "risk_score": risk,
            }))
            write_manifest(run_dir, {"dataset_version": f"v1.1-{version}-features", "feature_store_version": "1.0.0", "feature_spec_version": "1.0.0", "label_spec_version": "1.0.0"})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "survival", "label": SURVIVAL_LABEL, "model": name, "feature_set": version, "split": split_name, **metrics})
    return rows


def _load(version: str) -> tuple[pd.DataFrame, dict]:
    path = DATASET_V1_0 if version == "v1.0" else DATASET_V1_1
    manifest_path = MANIFEST_V1_0 if version == "v1.0" else MANIFEST_V1_1
    return pd.read_parquet(path), json.loads(manifest_path.read_text(encoding="utf-8"))


def main() -> None:
    rows: list[dict] = []
    for version in ("v1.0", "v1.1"):
        dataset, manifest = _load(version)
        rows += _run_regression(dataset, manifest, version)
        for label in BINARY_LABELS:
            rows += _run_binary(dataset, manifest, label, version)
        rows += _run_survival(dataset, manifest, version)

    comparison = pd.DataFrame(rows).sort_values(["task", "label", "feature_set", "model", "split"])
    comparison.to_csv(EXPERIMENTS_ROOT / "comparison.csv", index=False)

    summary = ["# V1.1 comparison — v1.0 vs v1.1 (physics + measured geometry)", ""]
    metric_key = {"regression": "rmse", "binary": "pr_auc", "survival": "c_index"}
    for task in ("regression", "binary", "survival"):
        summary.append(f"## {task}")
        summary.append("")
        sub = comparison[comparison["task"] == task]
        for (label, split), grp in sub.groupby(["label", "split"]):
            summary.append(f"### {label} · {split}")
            summary.append("")
            summary.append("| model | feature_set | {m} |".format(m=metric_key[task]))
            summary.append("| --- | --- | --- |")
            for _, r in grp.sort_values(["model", "feature_set"]).iterrows():
                summary.append(f"| {r['model']} | {r['feature_set']} | {r.get(metric_key[task]):.4f} |")
            summary.append("")
    (EXPERIMENTS_ROOT / "comparison_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"ran {len(rows)} experiment evaluations -> {EXPERIMENTS_ROOT}")
    pivot = comparison[comparison["split"] == "test"].pivot_table(
        index=["task", "label", "model"], columns="feature_set",
        values=["rmse", "pr_auc", "c_index"], aggfunc="first",
    )
    print(pivot.round(4).to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="delete the v1.1 experiment registry before running")
    args = parser.parse_args()
    if args.clean and EXPERIMENTS_ROOT.exists():
        import shutil
        shutil.rmtree(EXPERIMENTS_ROOT)
        print(f"removed {EXPERIMENTS_ROOT}")
    main()
