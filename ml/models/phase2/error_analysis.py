"""WS3 — structured error analysis on the WS1 LightGBM champion (v2.0 test split).

Uses persisted test predictions from the benchmark registry (no refit, no train
leak). Joins to context (home shed, wheel profile, turning, RTIS coverage,
interval length, exposure_v2/physics_v2 availability) and emits:

  * Overall + sign-stratified error decomposition (positive/negative residual).
  * Worst-100 rows with full context (the "hard cases").
  * Strata-stratified RMSE enrichment per strata column (worst strata).
  * Turning/artifact hypothesis: are extreme residuals coincident with turning
    events or interval anomalies?
  * Exposure-window effect: error by calendar year bucket (gating confound).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"
LIGHTGBM_TEST_EXP = EXPERIMENTS_ROOT / "benchmark_grouped" / "experiment_0006"
OUT_DIR = EXPERIMENTS_ROOT / "error_analysis"
REGRESSION_LABEL = "next_interval_dia_delta_mm"

STRATA_COLUMNS = {
    "home_shed": "home shed",
    "wheel_profile_2class": "wheel profile",
    "interval_days_bucket": "interval length",
    "turning_indicator_raw": "turning this interval",
    "rtis_coverage_bucket": "RTIS coverage %",
    "calendar_year": "interval end year",
    "exposure_available": "exposure_v2 available",
}


def _load():
    dataset = pd.read_parquet(DATASET_PATH)
    preds = pd.read_parquet(LIGHTGBM_TEST_EXP / "predictions.parquet")
    cfg = json.loads((LIGHTGBM_TEST_EXP / "config.json").read_text())
    return dataset, preds, cfg


def _buckets(df: pd.DataFrame) -> pd.DataFrame:
    def _qbin(series, name, qs=5, na_label="<NA>"):
        qcut = pd.qcut(series.rank(method="first"), qs, labels=[f"{name} Q{i+1}" for i in range(qs)])
        return qcut.astype("string").fillna(na_label)

    df = df.copy()
    df["interval_days_bucket"] = _qbin(df["interval_days"], "interval")
    df["rtis_coverage_bucket"] = _qbin(df["rtis_reporting_coverage_pct"], "coverage")
    df["calendar_year"] = pd.to_datetime(df["next_interval_end_timestamp"]).dt.year.astype(int)
    df["exposure_available"] = df["interval_distance_km"].notna().map(
        {True: "exposure_v2 present", False: "exposure_v2 absent"})
    return df


def _stratified(df: pd.DataFrame, label_col: str) -> list[dict]:
    rows = []
    for col, disp in STRATA_COLUMNS.items():
        grp = df.groupby(col, dropna=False)[label_col]
        for key, sub in df.groupby(col, dropna=False):
            if len(sub) < 30:
                continue
            rows.append({"stratum": disp, "level": str(key), "n": len(sub),
                         "rmse": float(np.sqrt(np.mean(sub[label_col] ** 2))),
                         "mae": float(np.mean(sub[label_col].abs())),
                         "sign_err": float(np.mean(sub[label_col] > 0))})
    return rows


def _worst_100(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    df = df.copy()
    df["abs_error"] = df[label_col].abs()
    return df.nlargest(100, "abs_error")


def main() -> None:
    dataset, preds, cfg = _load()
    merged = dataset.merge(preds, on="operational_exposure_id", suffixes=("", "_y"))
    merged = merged[merged["split"] == "test"].copy()
    merged = _buckets(merged)
    merged["residual"] = merged["y_true"] - merged["y_pred"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    overall = {
        "rmse": float(np.sqrt(np.mean(merged["residual"] ** 2))),
        "mae": float(np.mean(merged["residual"].abs())),
        "sign_err_rate": float(np.mean(merged["residual"] > 0)),
        "n": len(merged),
    }
    (OUT_DIR / "overall.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")

    worst = _worst_100(merged, "residual")
    cols = ["operational_exposure_id", "y_true", "y_pred", "residual",
            "next_interval_end_timestamp", "home_shed", "wheel_profile_2class",
            "turning_indicator_raw", "days_since_turning", "interval_days",
            "rtis_reporting_coverage_pct", "interval_distance_km", "running_hours_proxy",
            "wear_per_1000km_s1", "exposure_index_s1", "next_interval_turning_flag"]
    worst[cols].to_csv(OUT_DIR / "worst_100.csv", index=False)

    strata = pd.DataFrame(_stratified(merged, "residual"))
    strata.to_csv(OUT_DIR / "strata_rmse.csv", index=False)

    # Turning/artifact hypothesis: residual distribution around turning events.
    turning = merged[merged["turning_indicator_raw"] == 1]
    no_turning = merged[merged["turning_indicator_raw"] == 0]
    hyp = {
        "turning_n": len(turning), "no_turning_n": len(no_turning),
        "turning_rmse": float(np.sqrt(np.mean(turning["residual"] ** 2))),
        "no_turning_rmse": float(np.sqrt(np.mean(no_turning["residual"] ** 2))),
        "turning_mae": float(np.mean(turning["residual"].abs())),
        "no_turning_mae": float(np.mean(no_turning["residual"].abs())),
    }
    (OUT_DIR / "turning_hypothesis.json").write_text(json.dumps(hyp, indent=2), encoding="utf-8")

    # Exposure-window effect: per-year RMSE (confound check).
    yearly = (merged.groupby("calendar_year")["residual"]
                    .agg(lambda s: float(np.sqrt(np.mean(s ** 2))))
                    .rename("rmse").reset_index())
    yearly["n"] = merged.groupby("calendar_year").size().values
    yearly.to_csv(OUT_DIR / "yearly_rmse.csv", index=False)

    # Sign-stratified decomposition: are large +errors (over-predicting wear) different?
    pos = merged[merged["residual"] > 0]
    neg = merged[merged["residual"] < 0]
    sign = pd.DataFrame([
        {"sign": "positive (over-predict wear)", "n": len(pos),
         "rmse": float(np.sqrt(np.mean(pos["residual"] ** 2))),
         "mean_residual": float(pos["residual"].mean()),
         "median_exposure_avail": float(pos["interval_distance_km"].notna().mean())},
        {"sign": "negative (under-predict wear)", "n": len(neg),
         "rmse": float(np.sqrt(np.mean(neg["residual"] ** 2))),
         "mean_residual": float(neg["residual"].mean()),
         "median_exposure_avail": float(neg["interval_distance_km"].notna().mean())},
    ])
    sign.to_csv(OUT_DIR / "sign_stratified.csv", index=False)

    _report(overall, hyp, strata, yearly, sign)
    print(f"-> {OUT_DIR}: worst_100.csv, strata_rmse.csv, turning_hypothesis.json, "
          f"sign_stratified.csv, yearly_rmse.csv, error_analysis_report.md")


def _report(overall, hyp, strata, yearly, sign) -> None:
    lines = [
        "# WS3 Error Analysis — LightGBM test split (v2.0)",
        "",
        f"Source: benchmark_grouped/experiment_0006 (lightgbm, seed 42). "
        f"Overall RMSE={overall['rmse']:.3f}, MAE={overall['mae']:.3f}, "
        f"over-predict rate={overall['sign_err_rate']:.3f}.",
        "",
        "## Sign-stratified error",
        "",
        "| sign | n | RMSE | mean residual | exposure present % |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for _, r in sign.iterrows():
        lines.append(f"| {r['sign']} | {r['n']} | {r['rmse']:.3f} | {r['mean_residual']:.3f} | "
                     f"{r['median_exposure_avail']:.3f} |")
    lines += [
        "",
        "## Worst strata (by RMSE)",
        "",
        "| stratum | level | n | RMSE | over-predict % |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    top = strata.sort_values("rmse", ascending=False).head(15)
    for _, r in top.iterrows():
        lines.append(f"| {r['stratum']} | {r['level']} | {r['n']} | {r['rmse']:.3f} | {r['sign_err']:.3f} |")
    lines += [
        "",
        "## Turning/artifact hypothesis",
        "",
        f"- Turning intervals: n={hyp['turning_n']}, RMSE={hyp['turning_rmse']:.3f}",
        f"- Non-turning: n={hyp['no_turning_n']}, RMSE={hyp['no_turning_rmse']:.3f}",
        "",
        "## Yearly RMSE (exposure-window confound)",
        "",
        "| year | n | RMSE |",
        "| --- | ---: | ---: |",
    ]
    for _, r in yearly.iterrows():
        lines.append(f"| {r['calendar_year']} | {r['n']} | {r['rmse']:.3f} |")
    lines += [
        "",
        "## Caveats",
        "",
        "- Pre-2023 rows have no exposure_v2/physics_v2 signal; their error is driven by",
        "  geometry/physics legacy features only (see feature_availability_report.md).",
        "- Worst-100 rows are enumerated in worst_100.csv for manual inspection."]
    (OUT_DIR / "error_analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
