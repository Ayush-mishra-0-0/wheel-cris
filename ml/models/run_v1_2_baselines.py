"""V1.2 model comparison — label cleanup effect, isolated.

Isolates the ONLY difference v1.2 introduces (quarantined training labels):
  - v1_1_train : X from v1.1 train rows (INCLUDES the 55 sentinel train labels)
  - v1_2_train : X from v1.2 train rows (sentinels quarantined, 55 fewer rows)
Both feature matrices are byte-identical on the retained rows, so the comparison
measures only the training-label-cleanup effect. Both are evaluated on the SAME
eval sets (v1.2 val / v1.2 test, 28,065 test rows — sentinel-free), so the test
numbers are directly comparable to the v1.1 report's 28,066-row test modulo the
1 quarantined test sentinel.

Task: regression (`next_interval_dia_delta_mm`) — the only label the quarantine
touches. Outputs models/experiments/v1.2/comparison.csv + comparison_summary.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
DATASET_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
MANIFEST_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_manifest_v1.2.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v1.2"
RANDOM_STATE = 42
REGRESSION_LABEL = "next_interval_dia_delta_mm"


def _importance(model, x_columns, eval_set, label):
    try:
        from sklearn.inspection import permutation_importance
        perm = permutation_importance(model, eval_set[x_columns], eval_set[label],
                                      n_repeats=3, random_state=42, scoring="neg_mean_squared_error", n_jobs=-1)
        rank = pd.Series(perm.importances_mean, index=x_columns).sort_values(ascending=False)
        return {"kind": "permutation_importance", "scorer": "neg_mean_squared_error", "top_30": rank.head(30).to_dict()}
    except Exception:
        return {"kind": "unavailable"}


def main() -> None:
    d11 = pd.read_parquet(DATASET_V1_1)
    d12 = pd.read_parquet(DATASET_V1_2)
    manifest = json.loads(MANIFEST_V1_2.read_text(encoding="utf-8"))
    x_columns = [c for c, r in manifest["column_roles"].items() if r == "feature"]

    train_v11 = d11[d11["split"] == "train"]
    train_v12 = d12[d12["split"] == "train"]

    estimators = [
        ("dummy_mean", DummyRegressor(strategy="mean")),
        ("linear", LinearRegression()),
        ("elastic_net", make_pipeline(StandardScaler(), ElasticNet(max_iter=10000, random_state=RANDOM_STATE))),
        ("hist_gradient_boosting", HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE, early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)),
        ("random_forest", RandomForestRegressor(n_estimators=150, max_depth=18, min_samples_leaf=25, n_jobs=-1, random_state=RANDOM_STATE)),
    ]

    rows = []
    for train_name, train_df in (("v1_1_train", train_v11), ("v1_2_train", train_v12)):
        print(f"[{train_name}] train rows = {len(train_df):,} (sentinel labels {'included' if train_name == 'v1_1_train' else 'quarantined'})")
        for split_name in ("val", "test"):
            eval_set = d12[d12["split"] == split_name]
            for model_name, estimator in estimators:
                estimator.fit(train_df[x_columns], train_df[REGRESSION_LABEL])
                y_pred = estimator.predict(eval_set[x_columns])
                metrics = evaluate.regression_metrics(eval_set[REGRESSION_LABEL], y_pred)
                config = {"phase": "v1.2", "task": "regression", "label": REGRESSION_LABEL,
                          "model": model_name, "train_condition": train_name,
                          "split_contract": "grouped temporal (v1.2 eval rows), train rows differ by quarantine",
                          "eval_set": f"v1.2-{split_name}", "random_state": RANDOM_STATE}
                experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "regression", config)
                write_metrics(run_dir, {split_name: metrics})
                write_feature_importance(run_dir, _importance(estimator, x_columns, eval_set, REGRESSION_LABEL))
                write_model(run_dir, estimator)
                write_predictions(run_dir, pd.DataFrame({
                    "operational_exposure_id": eval_set["operational_exposure_id"],
                    "split": split_name, "y_true": eval_set[REGRESSION_LABEL], "y_pred": y_pred,
                }))
                write_manifest(run_dir, {"dataset_version": "v1.2",
                                         "train_dataset_version": "v1.1" if train_name == "v1_1_train" else "v1.2",
                                         "feature_store_version": "1.0.0", "feature_spec_version": "1.0.0",
                                         "label_spec_version": "1.0.1"})
                rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "regression",
                             "label": REGRESSION_LABEL, "model": model_name, "train_condition": train_name,
                             "split": split_name, **metrics})
                print(f"  {model_name:24s} {split_name}: RMSE={metrics['rmse']:.4f}  MAE={metrics['mae']:.4f}")

    comparison = pd.DataFrame(rows).sort_values(["train_condition", "model", "split"])
    comparison.to_csv(EXPERIMENTS_ROOT / "comparison.csv", index=False)

    summary = [
        "# V1.2 comparison — label cleanup effect (v1.1-train vs v1.2-train, same v1.2 test)",
        "",
        f"Eval rows: v1.2 val={len(d12[d12['split']=='val']):,} · v1.2 test={len(d12[d12['split']=='test']):,} "
        f"(v1.1 test was 28,066; the 1 sentinel test row is quarantined in v1.2).",
        "",
        "| train_condition | train rows |",
        "| --- | ---: |",
        f"| v1_1_train | {len(train_v11):,} (55 sentinel train labels included) |",
        f"| v1_2_train | {len(train_v12):,} (sentinels quarantined) |",
        "",
    ]
    for split_name in ("val", "test"):
        sub = comparison[comparison["split"] == split_name]
        summary.append(f"## {split_name}")
        summary.append("")
        summary.append("| model | RMSE v1_1_train | RMSE v1_2_train | MAE v1_1_train | MAE v1_2_train | ΔRMSE | ΔMAE |")
        summary.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for model_name, grp in sub.groupby("model"):
            g = grp.set_index("train_condition")
            r11, r12 = g.loc["v1_1_train", "rmse"], g.loc["v1_2_train", "rmse"]
            m11, m12 = g.loc["v1_1_train", "mae"], g.loc["v1_2_train", "mae"]
            summary.append(f"| {model_name} | {r11:.3f} | {r12:.3f} | {m11:.3f} | {m12:.3f} | {(r12-r11)/r11*100:+.1f}% | {(m12-m11)/m11*100:+.1f}% |")
        summary.append("")
    (EXPERIMENTS_ROOT / "comparison_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"\nwrote {len(rows)} experiment evaluations -> {EXPERIMENTS_ROOT}")


if __name__ == "__main__":
    main()
