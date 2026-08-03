"""Phase 4 — structured error analysis of the best baseline model per task/label.

Uses the grouped-temporal TEST split predictions (never touches train).
Joins predictions to context (home shed, wheel profile, interval length,
turning events, RTIS coverage, wear) and emits worst-100 rows plus a
strata-stratified comparison per (task, label).

Follows configs/evaluation_spec.json > reporting > error_analysis:
"worst-100-rows diagnostics stratified by shed, wheel profile, interval length,
 turning events, missing RTIS, extreme wear (Phase 4, not SHAP-only)".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "model_datasets" / "v1.0"
DATASET_PATH = DATA_DIR / "model_dataset_v1.0.parquet"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments"
OUT_DIR = EXPERIMENTS_ROOT / "error_analysis"

SUBJECT_KEY = "operational_exposure_id"

# Strata used to stratify the worst rows. Values are display labels; the keys
# refer to columns ON df (continuous ones are pre-bucketed in _add_buckets).
STRATA_COLUMNS = {
    "home_shed": "home shed",
    "wheel_profile_2class": "wheel profile",
    "interval_days_bucket": "interval length (days)",
    "turning_indicator_raw": "turning event this interval",
    "rtis_coverage_bucket": "RTIS reporting coverage %",
    "wear_side1_bucket": "interval wear, side 1 (mm)",
    "wear_side2_bucket": "interval wear, side 2 (mm)",
}

# Best real-model experiment per (task, label) from comparison.csv (test split).
MODEL_CHOICE = {
    ("binary", "next_interval_large_loss_flag"): "hist_gradient_boosting",
    ("binary", "next_interval_turning_flag"): "hist_gradient_boosting",
    ("regression", "next_interval_dia_delta_mm"): "hist_gradient_boosting",
    ("survival", "time_to_next_turning_days"): "hist_gradient_boosting_observed_only",
}


def _load_source(dataset, store_meta):
    """Merge predictions to context. Returns (predictions+context, experiment dir)."""
    out = {}
    return out


def _select(context_df, experiment_root) -> pd.DataFrame:
    return context_df


def _add_buckets(df):
    """Bucket continuous strata into quantile-based bins so enrichment is meaningful."""
    def _qbin(series, name, qs=5, na_label="<NA>"):
        qcut = pd.qcut(series.rank(method="first"), qs, labels=[f"{name} Q{i+1}" for i in range(qs)])
        return qcut.astype("string").fillna(na_label)

    df["interval_days_bucket"] = _qbin(df["interval_days"], "interval")
    df["rtis_coverage_bucket"] = _qbin(df["rtis_reporting_coverage_pct"], "coverage")
    df["wear_side1_bucket"] = _qbin(df["diameter_delta_raw_mm_side_1"], "wear1")
    df["wear_side2_bucket"] = _qbin(df["diameter_delta_raw_mm_side_2"], "wear2")
    return df


def _add_error(df, task):
    """Add a scalar `error` column for ranking worst rows."""
    if task == "regression":
        df["error"] = (df["y_true"] - df["y_pred"]).abs()
    elif task == "binary":
        df["error"] = (df["y_true"] - df["y_prob"]).abs()
    elif task == "survival":
        # risk_score = -predicted time to event; error in observed-time space is
        # only defined for the uncensored rows (censored rows have NaN time).
        df["error"] = (df["time_to_event"] - (-df["risk_score"])).abs()
    else:
        raise ValueError(task)
    return df


def _worst_rows(df, n=100):
    return df.nlargest(n, "error")


def _stratify(df, worst, n=100):
    """For each stratum column: worst-100 split by value vs the same column on the
    full test set, so we can see which slices are over-represented in the errors."""
    rows = []
    for col, label in STRATA_COLUMNS.items():
        if col not in df.columns:
            print(f"  missing stratum column: {col}")
            continue
        full_share = df[col].value_counts(dropna=False, normalize=True)
        worst_share = worst[col].value_counts(dropna=False, normalize=True)
        for value, worst_fraction in worst_share.items():
            full_fraction = float(full_share.get(value, 0.0))
            is_nan = (isinstance(value, float) and pd.isna(value)) or value is None or (isinstance(value, str) and value == "nan")
            g = worst[pd.isna(worst[col])] if is_nan else worst[worst[col] == value]
            rows.append({
                "stratum": label, "feature": col, "value": "<NA>" if is_nan else str(value),
                "worst_n": int(len(g)),
                "worst_fraction": round(float(worst_fraction), 4),
                "full_test_fraction": round(full_fraction, 4),
                "enrichment": round(float(worst_fraction / full_fraction), 2) if full_fraction > 0 else None,
            })
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = pd.read_parquet(DATASET_PATH)
    store = pd.read_parquet(STORE_PATH)
    comparison = pd.read_csv(EXPERIMENTS_ROOT / "comparison.csv")

    # Source columns to expose for error analysis.
    exposed = ["operational_exposure_id", "split",
               "interval_days", "diameter_delta_raw_mm_side_1", "diameter_delta_raw_mm_side_2",
               "rtis_reporting_coverage_pct", "turning_indicator_raw", "days_since_turning",
               "wheel_profile_2class", "locomotive_number"]
    context = dataset[exposed].merge(
        store[["operational_exposure_id", "home_shed", "defect_zone", "defect_division"]],
        on=SUBJECT_KEY, how="left", suffixes=("", "_store")
    )
    store_cols = [c for c in ["home_shed", "defect_zone", "defect_division"] if f"{c}_store" in context.columns]
    for c in store_cols:
        context[c] = context[c].fillna(context[f"{c}_store"])
    context.drop(columns=[f"{c}_store" for c in store_cols], errors="ignore", inplace=True)

    rows_by_task= {}
    for (task, label), model in MODEL_CHOICE.items():
        comparison_row = comparison[(comparison["task"] == task) & (comparison["label"] == label) & (comparison["model"] == model) & (comparison["split"] == "test")]
        if len(comparison_row) != 1:
            print(f"skip {task}/{label}: no single test run for {model}")
            continue
        experiment = comparison_row.iloc[0]["experiment"]
        exp_dir = EXPERIMENTS_ROOT / task / experiment
        pred = pd.read_parquet(exp_dir / "predictions.parquet")
        pred = pred[pred["split"] == "test"]

        df = pred.merge(context, on="operational_exposure_id", how="left")
        df = _add_buckets(df)
        df = _add_error(df, task)

        worst = _worst_rows(df)
        worst.round(4).to_csv(OUT_DIR / f"worst_{task}_{label}_rows.csv", index=False)

        strat = _stratify(df, worst)
        strat.to_csv(OUT_DIR / f"strat_{task}_{label}.csv", index=False)

        # Manual: enumerate the top-3 most enriched strata.
        strat_sorted = strat.sort_values("enrichment", ascending=False, na_position="last")
        top_strata = strat_sorted.head(6)[["stratum", "value", "worst_n", "enrichment"]].to_dict("records") if len(strat_sorted) else []
        rows_by_task.setdefault(task, []).append({
            "label": label, "experiment": experiment,
            "model": model, "test_n": int(len(df)),
            "worst_100_saved": f"worst_{task}_{label}_rows.csv",
            "stratification_saved": f"strat_{task}_{label}.csv",
            "top_enriched_strata": top_strata,
        })
        print(f"{task}/{label}: {len(df)} test rows; worst-100 saved; {len(strat)} strata rows")

    (OUT_DIR / "error_analysis_index.json").write_text(json.dumps(rows_by_task, indent=2), encoding="utf-8")
    print(f"error analysis written -> {OUT_DIR}")


if __name__ == "__main__":
    main()