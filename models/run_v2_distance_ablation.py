"""V2 distance-x ablation — does experimental RTIS interval distance move HGB?

Compares two feature sets on the SAME v1.2 train/val/test rows:
  - baseline : the 96 released v1.2 features
  - +distance : baseline + interval_distance_km_experimental,
                rtis_distance_coverage_days, rtis_distance_coverage_pct
                (EXPERIMENTAL, from build_distance_experimental.py — not a
                Feature Store release; released distance feature stays BLOCKED)

Task: regression (next_interval_dia_delta_mm), champion HGB config from
run_v1_2_baselines. Outputs models/experiments/v1.2/distance_ablation.csv +
distance_ablation_summary.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
DISTANCE_X = PROJECT_ROOT / "model_datasets" / "v1.2" / "distance_experimental.parquet"
MANIFEST_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_manifest_v1.2.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v1.2"
RANDOM_STATE = 42
REGRESSION_LABEL = "next_interval_dia_delta_mm"
DISTANCE_FEATURES = [
    "interval_distance_km_experimental",
    "rtis_distance_coverage_days",
    "rtis_distance_coverage_pct",
]


def _champion_hgb():
    return HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=20,
    )


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
    d12 = pd.read_parquet(DATASET_V1_2)
    dist = pd.read_parquet(DISTANCE_X)
    manifest = json.loads(MANIFEST_V1_2.read_text(encoding="utf-8"))
    base_features = [c for c, r in manifest["column_roles"].items() if r == "feature"]

    dataset = d12.merge(dist, on="operational_exposure_id", how="left", validate="one_to_one")
    assert len(dataset) == len(d12), "distance join must be one-to-one"

    train = dataset[dataset["split"] == "train"]
    test = dataset[dataset["split"] == "test"]

    feature_sets = [
        ("baseline", base_features),
        ("baseline_plus_distance", base_features + DISTANCE_FEATURES),
    ]

    rows = []
    for set_name, x_cols in feature_sets:
        print(f"[{set_name}] {len(x_cols)} features; train rows = {len(train):,}")
        model = _champion_hgb()
        model.fit(train[x_cols], train[REGRESSION_LABEL])
        y_pred = model.predict(test[x_cols])
        metrics = evaluate.regression_metrics(test[REGRESSION_LABEL], y_pred)
        config = {"phase": "v2.distance-x", "task": "regression", "label": REGRESSION_LABEL,
                  "model": "hist_gradient_boosting", "feature_set": set_name,
                  "split_contract": "grouped temporal (v1.2 train/test, identical rows)",
                  "eval_set": "v1.2-test", "distance_status": "EXPERIMENTAL_NOT_RELEASED",
                  "random_state": RANDOM_STATE}
        experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "regression", config)
        write_metrics(run_dir, {"test": metrics})
        write_feature_importance(run_dir, _importance(model, x_cols, test, REGRESSION_LABEL))
        write_model(run_dir, model)
        write_predictions(run_dir, pd.DataFrame({
            "operational_exposure_id": test["operational_exposure_id"],
            "split": "test", "y_true": test[REGRESSION_LABEL], "y_pred": y_pred,
        }))
        write_manifest(run_dir, {"dataset_version": "v1.2", "feature_store_version": "1.0.0",
                                 "feature_spec_version": "1.0.0", "label_spec_version": "1.0.1",
                                 "experimental_features": DISTANCE_FEATURES,
                                 "experimental_provenance": "models/build_distance_experimental.py (dedupe loco+date+division+distance, sum over (start,end], coverage-days denominator)"})
        rows.append({"experiment": f"experiment_{experiment_id:04d}", "feature_set": set_name,
                     "n_features": len(x_cols), **metrics})
        print(f"  {set_name:26s} test RMSE={metrics['rmse']:.4f}  MAE={metrics['mae']:.4f}  R2={metrics.get('r2'):.4f}")

    comparison = pd.DataFrame(rows).set_index("feature_set")
    comparison.to_csv(EXPERIMENTS_ROOT / "distance_ablation.csv")

    baseline, plus = comparison.loc["baseline"], comparison.loc["baseline_plus_distance"]
    delta_rmse = (plus["rmse"] - baseline["rmse"]) / baseline["rmse"] * 100
    delta_mae = (plus["mae"] - baseline["mae"]) / baseline["mae"] * 100
    summary = [
        "# V2 distance-x ablation — experimental RTIS interval distance (HGB, v1.2 test)",
        "",
        f"Eval rows: v1.2 test = {len(test):,}.  Same train rows ({len(train):,}) and same",
        "test rows for both feature sets; the ONLY difference is the 3 experimental",
        "distance columns. Released distance feature stays BLOCKED; these are",
        "experimental only, to size whether distance exposure can move predictions.",
        "",
        f"Deduped-distance coverage: {dataset['interval_distance_km_experimental'].notna().mean()*100:.1f}% of intervals have reports;",
        f"median interval distance (when reported) = {dataset['interval_distance_km_experimental'].median():,.0f} km.",
        "",
        "| feature_set | n_features | RMSE | MAE | R² |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| baseline | {int(baseline['n_features'])} | {baseline['rmse']:.3f} | {baseline['mae']:.3f} | {baseline['r2']:.3f} |",
        f"| baseline_plus_distance | {int(plus['n_features'])} | {plus['rmse']:.3f} | {plus['mae']:.3f} | {plus['r2']:.3f} |",
        "",
        f"ΔRMSE {delta_rmse:+.2f}% · ΔMAE {delta_mae:+.2f}% (negative = distance helps).",
        "",
        "Verdict: a meaningful (>= ~1%) improvement on an already-tuned champion",
        "justifies a v2.x experiment + the data-team nod for the released feature.",
        "",
    ]
    (EXPERIMENTS_ROOT / "distance_ablation_summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"\nwrote -> {EXPERIMENTS_ROOT / 'distance_ablation_summary.md'}")


if __name__ == "__main__":
    main()
