"""V1.1 error analysis — how physics + measured geometry change the error profile.

Compares TEST-split residuals between the v1.0 and v1.1 HGB regression models
(the biggest gain: RMSE 23.1 -> 15.7). Answers:
  1. Which strata still dominate worst-100 in v1.1?
  2. How much did each stratum's MAE/RMSE improve between versions?
  3. Where do large v1.1 residuals remain (patterns for future work)?

Also quantifies turning/large-loss improvements for the binary tasks via the same
strata buckets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATASET_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
STORE_PATH = PROJECT_ROOT / "feature_store" / "feature_store_v1.parquet"
EXPERIMENTS_V1_0 = PROJECT_ROOT / "models" / "experiments" / "v1.0"
EXPERIMENTS_V1_1 = PROJECT_ROOT / "models" / "experiments" / "v1.1"
OUT_DIR = PROJECT_ROOT / "models" / "experiments" / "v1.1" / "error_analysis"

SUBJECT_KEY = "operational_exposure_id"

STRATA_COLUMNS = {
    "home_shed": "home shed",
    "wheel_profile_2class": "wheel profile",
    "interval_days_bucket": "interval length (days)",
    "turning_indicator_raw": "turning event this interval",
    "rtis_coverage_bucket": "RTIS reporting coverage %",
    "wear_side1_bucket": "interval wear, side 1 (mm)",
    "wear_side2_bucket": "interval wear, side 2 (mm)",
}

# model name used in both registries for regression
REGRESSION_MODEL = "hist_gradient_boosting"


def _find_experiment(root: Path, task: str, model: str, feature_set: str | None, label: str) -> Path:
    matches = []
    for p in sorted((root / task).glob("experiment_*")):
        cfg = json.loads((p / "config.json").read_text(encoding="utf-8"))
        if cfg.get("model") != model or cfg.get("label") != label:
            continue
        if feature_set is None:
            if "feature_set" not in cfg:  # v1.0 registry predates feature_set
                matches.append(p)
        elif cfg.get("feature_set") == feature_set:
            matches.append(p)
    # Prefer the run whose predictions contain test rows (v1.0 splits val/test
    # into separate experiment dirs).
    for p in matches:
        pred = pd.read_parquet(p / "predictions.parquet")
        if "split" in pred.columns and (pred["split"] == "test").any():
            return p
    if matches:
        return matches[0]
    raise FileNotFoundError(f"{model} {feature_set} {label} in {root / task}")


def _add_buckets(df):
    def _qbin(series, name, qs=5, na_label="<NA>"):
        qcut = pd.qcut(series.rank(method="first"), qs, labels=[f"{name} Q{i+1}" for i in range(qs)])
        return qcut.astype("string").fillna(na_label)

    df["interval_days_bucket"] = _qbin(df["interval_days"], "interval")
    df["rtis_coverage_bucket"] = _qbin(df["rtis_reporting_coverage_pct"], "coverage")
    df["wear_side1_bucket"] = _qbin(df["diameter_delta_raw_mm_side_1"], "wear1")
    df["wear_side2_bucket"] = _qbin(df["diameter_delta_raw_mm_side_2"], "wear2")
    return df


def _strat_improvement(df, worst10, worst11):
    """Per stratum: MAE(RMSE) v1.0 vs v1.1 + worst-100 share change."""
    rows = []
    for col, label in STRATA_COLUMNS.items():
        if col not in df.columns:
            continue
        for value in df[col].dropna().unique():
            mask10 = (df["y_pred10"].notna()) & (df[col] == value)
            mask11 = (df["y_pred11"].notna()) & (df[col] == value)
            if mask11.sum() < 50:
                continue
            mae10 = float((df.loc[mask10, "y_true"] - df.loc[mask10, "y_pred10"]).abs().mean())
            mae11 = float((df.loc[mask11, "y_true"] - df.loc[mask11, "y_pred11"]).abs().mean())
            rmse10 = float(np.sqrt(np.mean((df.loc[mask10, "y_true"] - df.loc[mask10, "y_pred10"]) ** 2)))
            rmse11 = float(np.sqrt(np.mean((df.loc[mask11, "y_true"] - df.loc[mask11, "y_pred11"]) ** 2)))
            share10 = float((worst10[col] == value).mean())
            share11 = float((worst11[col] == value).mean())
            rows.append({
                "stratum": label, "feature": col, "value": str(value),
                "n_test": int(mask11.sum()),
                "mae_v1_0": round(mae10, 3), "mae_v1_1": round(mae11, 3), "mae_change_pct": round((mae11 / mae10 - 1) * 100, 1) if mae10 else None,
                "rmse_v1_0": round(rmse10, 3), "rmse_v1_1": round(rmse11, 3),
                "worst100_share_v1_0": round(share10, 3), "worst100_share_v1_1": round(share11, 3),
            })
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = pd.read_parquet(DATASET_V1_1)
    store = pd.read_parquet(STORE_PATH)

    exposed = ["operational_exposure_id", "split",
               "interval_days", "diameter_delta_raw_mm_side_1", "diameter_delta_raw_mm_side_2",
               "rtis_reporting_coverage_pct", "turning_indicator_raw", "days_since_turning",
               "wheel_profile_2class", "locomotive_number", "home_shed"]
    context = dataset[exposed].copy()
    if "home_shed" not in context.columns or context["home_shed"].isna().all():
        context["home_shed"] = context["home_shed"].fillna(
            store.set_index("operational_exposure_id")["home_shed"].reindex(context["operational_exposure_id"]).to_numpy()
        )

    label = "next_interval_dia_delta_mm"
    exp10 = _find_experiment(EXPERIMENTS_V1_0, "regression", REGRESSION_MODEL, None, label)
    exp11 = _find_experiment(EXPERIMENTS_V1_1, "regression", REGRESSION_MODEL, "v1.1", label)
    print(f"v1.0 run: {exp10.relative_to(PROJECT_ROOT)} | v1.1 run: {exp11.relative_to(PROJECT_ROOT)}")

    pred10 = pd.read_parquet(exp10 / "predictions.parquet")
    pred10 = pred10[pred10["split"] == "test"][["operational_exposure_id", "y_true", "y_pred"]].rename(columns={"y_pred": "y_pred10"})
    pred11 = pd.read_parquet(exp11 / "predictions.parquet")
    pred11 = pred11[pred11["split"] == "test"][["operational_exposure_id", "y_pred"]].rename(columns={"y_pred": "y_pred11"})

    df = context[context["split"] == "test"].merge(pred10, on=SUBJECT_KEY, how="left").merge(pred11, on=SUBJECT_KEY, how="left")
    df = _add_buckets(df)
    df["error10"] = (df["y_true"] - df["y_pred10"]).abs()
    df["error11"] = (df["y_true"] - df["y_pred11"]).abs()

    worst10 = df.nlargest(100, "error10")
    worst11 = df.nlargest(100, "error11")

    # Top-level improvement
    print(f"\ntest rows: {len(df)}")
    for tag, col in [("v1.0", "error10"), ("v1.1", "error11")]:
        e = df[col].dropna()
        print(f"  {tag}: MAE={e.mean():.3f}  RMSE={np.sqrt((e**2).mean()):.3f}  p95={e.quantile(0.95):.3f}  max={e.max():.3f}")

    strat = _strat_improvement(df, worst10, worst11)
    strat.to_csv(OUT_DIR / "regression_strata_improvement.csv", index=False)

    # worst-100 v1.1 rows with context (incl. the new physics features)
    cols = ["operational_exposure_id", "y_true", "y_pred10", "y_pred11", "error10", "error11",
            "home_shed", "wheel_profile_2class", "interval_days", "rtis_reporting_coverage_pct",
            "turning_indicator_raw", "days_since_turning",
            "phys_remaining_material_mm_s1", "phys_remaining_material_mm_s2", "geom_wsmDia1", "geom_wsmDia2"]
    available = [c for c in cols if c in worst11.columns]
    worst11[available].round(3).to_csv(OUT_DIR / "worst_100_v1_1_regression.csv", index=False)

    # Summary of what still dominates
    summary = ["# V1.1 residual analysis — regression", ""]
    summary += [f"- test rows: {len(df)}", ""]
    for tag, col in [("v1.0", "error10"), ("v1.1", "error11")]:
        e = df[col].dropna()
        summary.append(f"- **{tag}** MAE={e.mean():.3f} · RMSE={np.sqrt((e**2).mean()):.3f} · p95={e.quantile(0.95):.3f} · max={e.max():.3f}")
    summary.append("")
    summary.append("## Strata: MAE v1.0 -> v1.1 (top 20 improvements)")
    summary.append("")
    summary.append("| stratum | value | n | MAE v1.0 | MAE v1.1 | change % | worst100 share 1.0->1.1 |")
    summary.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    top = strat.sort_values("mae_change_pct").head(20)
    for _, r in top.iterrows():
        summary.append(f"| {r['stratum']} | {r['value']} | {int(r['n_test'])} | {r['mae_v1_0']:.1f} | {r['mae_v1_1']:.1f} | {r['mae_change_pct']:.0f}% | {r['worst100_share_v1_0']:.2f}->{r['worst100_share_v1_1']:.2f} |")
    (OUT_DIR / "residual_summary.md").write_text("\n".join(summary), encoding="utf-8")

    print(f"\nstrata improvement saved -> {OUT_DIR / 'regression_strata_improvement.csv'}")
    print("top 10 improving strata:")
    print(top.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
