"""
Plot actual vs predicted wheel diameter over time, split by train/val/test.

Two plots are produced:
  1. Single-wheelset trajectory: actual diameter (line + split-colored points)
     with predicted-next-diameter overlaid as diamond markers, connected by a
     thin line to the actual point it was predicted from (so you can *see*
     the error, not just read an RMSE number).
  2. Fleet-level monthly aggregate: mean diameter per month per split, actual
     vs predicted, so you get a readable trend even though individual
     wheelsets are inspected irregularly (weeks/months apart).

Why "predicted diameter" and not just "predicted delta":
  Your released label is `next_interval_dia_delta_mm` (a CHANGE, not an
  absolute diameter). To plot it on the same axis as measured diameter, we
  reconstruct: predicted_next_diameter = actual_diameter_now + predicted_delta.

Why we retrain instead of loading a saved model:
  `models/experiment_registry.py` never persists the fitted model object
  (only config/metrics/predictions/importance), and `run_baselines.py` only
  writes predictions for val+test. To show train points too, this script
  retrains the identical hist_gradient_boosting config from comparison.csv
  on the train split and predicts on all three splits, so the whole thing is
  reproducible from the released model_dataset alone.

Versions:
  Defaults to v1.0. Pass `--version v1.1` for the physics-informed dataset
  (model_datasets/v1.1), or `--compare` to overlay v1.0 vs v1.1 in the
  fleet-monthly and scatter plots.

Run from the project root (the folder containing model_datasets/, data/,
feature_store/, models/).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# ---------------------------------------------------------------------------
# Paths — PROJECT_ROOT is resolved as the folder containing model_datasets/
# (works whether this script sits at the repo root or in notebooks/).
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next(
    (d for d in [_SCRIPT_DIR, *_SCRIPT_DIR.parents] if (d / "model_datasets").is_dir()),
    _SCRIPT_DIR,
)
MEASUREMENTS_PATH = PROJECT_ROOT / "data" / "bronze" / "wheel_measurements.parquet"
# Per-version plot output: reports/plots/<version>/ (compare overlays -> compare/).
PLOT_DIR = PROJECT_ROOT / "reports" / "plots"

LABEL = "next_interval_dia_delta_mm"
RANDOM_STATE = 42
SPLIT_COLORS = {"train": "#4C72B0", "val": "#DD8452", "test": "#55A868"}
VERSION_COLORS = {"v1.0": "#8C8C8C", "v1.1": "#55A868"}
# Show only the holdout split for a fair actual-vs-predicted comparison.
PLOT_SPLITS = ["test"]

VERSIONS = {
    "v1.0": {
        "dataset": PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_v1.0.parquet",
        "manifest": PROJECT_ROOT / "model_datasets" / "v1.0" / "model_dataset_manifest_v1.0.json",
    },
    "v1.1": {
        "dataset": PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet",
        "manifest": PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_manifest_v1.1.json",
    },
}


def _eval_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    """Filter to the evaluation split and keep rows with a measured next diameter."""
    return dataset.loc[
        dataset["split"].isin(PLOT_SPLITS) & dataset["actual_next_dia1"].notna() & dataset["predicted_next_dia1"].notna()
    ].copy()


def load_dataset_with_predictions(version: str = "v1.0") -> pd.DataFrame:
    """Load the model dataset, retrain the released baseline, predict on all rows."""
    dataset_path = VERSIONS[version]["dataset"]
    manifest_path = VERSIONS[version]["manifest"]
    dataset = pd.read_parquet(dataset_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = [c for c, role in manifest["column_roles"].items() if role == "feature"]

    train = dataset[dataset["split"] == "train"]
    model = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.1,
        random_state=RANDOM_STATE,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=20,
    )
    model.fit(train[features], train[LABEL])
    dataset["y_pred_delta"] = model.predict(dataset[features])

    # Reconstruct absolute diameter at every interval endpoint (side 1).
    measurements = pd.read_parquet(MEASUREMENTS_PATH, columns=["wsmId", "wsmDia1"])
    measurements["wsmId"] = pd.to_numeric(measurements["wsmId"], errors="coerce").astype("Int64")

    dataset = dataset.merge(
        measurements.rename(columns={"wsmId": "interval_end_measurement_id", "wsmDia1": "actual_end_dia1"}),
        on="interval_end_measurement_id",
        how="left",
    )
    dataset = dataset.merge(
        measurements.rename(columns={"wsmId": "next_interval_end_measurement_id", "wsmDia1": "actual_next_dia1"}),
        on="next_interval_end_measurement_id",
        how="left",
    )
    dataset["predicted_next_dia1"] = dataset["actual_end_dia1"] + dataset["y_pred_delta"]
    return dataset


def plot_single_wheelset(dataset: pd.DataFrame, version: str = "v1.0", equipment_ids: dict[str, int] | None = None) -> Path:
    """Actual diameter trajectory for one representative wheelset PER SPLIT.

    Splits here are wheelset-grouped (every row of a given wheelset_equipment_id
    belongs to the same split — see build_model_dataset.py's
    _assign_grouped_temporal_split), so no single wheelset spans train+val+test.
    Instead we pick the most-inspected wheelset within each split and plot all
    three trajectories on one shared time axis.
    """
    if equipment_ids is None:
        equipment_ids = {
            split_name: dataset.loc[dataset["split"] == split_name, "wheelset_equipment_id"]
            .value_counts()
            .idxmax()
            for split_name in PLOT_SPLITS
            if (dataset["split"] == split_name).any()
        }

    fig, ax = plt.subplots(figsize=(13, 6))

    for split_name, equipment_id in equipment_ids.items():
        wheel = dataset[dataset["wheelset_equipment_id"] == equipment_id].sort_values("interval_end_timestamp")
        color = SPLIT_COLORS[split_name]

        ax.plot(
            wheel["interval_end_timestamp"], wheel["actual_end_dia1"],
            color=color, linewidth=1.2, alpha=0.6, zorder=1,
        )
        ax.scatter(
            wheel["interval_end_timestamp"], wheel["actual_end_dia1"],
            color=color, s=45, zorder=3, label=f"Actual — {split_name} (eq {equipment_id})",
        )

        predicted = wheel.dropna(subset=["next_interval_end_timestamp", "predicted_next_dia1"])
        if predicted.empty:
            continue
        ax.scatter(
            predicted["next_interval_end_timestamp"], predicted["predicted_next_dia1"],
            facecolors="none", edgecolors=color, s=70, marker="D",
            linewidths=1.6, zorder=4, label=f"Predicted (next) — {split_name}",
        )
        for _, row in predicted.iterrows():
            ax.plot(
                [row["interval_end_timestamp"], row["next_interval_end_timestamp"]],
                [row["actual_end_dia1"], row["predicted_next_dia1"]],
                color=color, linewidth=0.7, alpha=0.5, zorder=2,
            )

    ax.set_xlabel("Time")
    ax.set_ylabel("Wheel diameter, side 1 (mm)")
    ax.set_title(f"Wheel diameter over time — holdout split actual vs predicted-next ({version})")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="best", fontsize=8, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = PLOT_DIR / version / "diameter_timeseries_wheelset_per_split.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_fleet_monthly_aggregate(dataset: pd.DataFrame, version: str = "v1.0") -> Path:
    """Mean actual vs predicted diameter per month, one line per split."""
    df = dataset.dropna(subset=["actual_end_dia1", "predicted_next_dia1", "next_interval_end_timestamp"]).copy()
    df["month"] = df["interval_end_timestamp"].dt.to_period("M").dt.to_timestamp()
    df["next_month"] = df["next_interval_end_timestamp"].dt.to_period("M").dt.to_timestamp()

    actual_monthly = df.groupby(["split", "month"])["actual_end_dia1"].mean().reset_index()
    predicted_monthly = df.groupby(["split", "next_month"])["predicted_next_dia1"].mean().reset_index()

    fig, ax = plt.subplots(figsize=(13, 6))
    for split_name in PLOT_SPLITS:
        a = actual_monthly[actual_monthly["split"] == split_name].sort_values("month")
        p = predicted_monthly[predicted_monthly["split"] == split_name].sort_values("next_month")
        if not a.empty:
            ax.plot(a["month"], a["actual_end_dia1"], color=SPLIT_COLORS[split_name],
                     linewidth=2, label=f"Actual — {split_name}")
        if not p.empty:
            ax.plot(p["next_month"], p["predicted_next_dia1"], color=SPLIT_COLORS[split_name],
                     linewidth=2, linestyle="--", alpha=0.8, label=f"Predicted — {split_name}")

    ax.set_xlabel("Month")
    ax.set_ylabel("Mean wheel diameter, side 1 (mm)")
    ax.set_title(f"Fleet-wide mean diameter over time — actual (solid) vs predicted-next (dashed) [{version}]")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="best", fontsize=8, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = PLOT_DIR / version / "diameter_timeseries_fleet_monthly.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_prediction_scatter(dataset: pd.DataFrame, version: str = "v1.0") -> Path:
    """Scatter of actual vs predicted diameter for the selected evaluation split."""
    df = _eval_dataset(dataset)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(df["predicted_next_dia1"], df["actual_next_dia1"], s=20, alpha=0.5, color=SPLIT_COLORS[PLOT_SPLITS[0]])

    min_val = min(df["predicted_next_dia1"].min(), df["actual_next_dia1"].min())
    max_val = max(df["predicted_next_dia1"].max(), df["actual_next_dia1"].max())
    ax.plot([min_val, max_val], [min_val, max_val], color="black", linestyle="--", linewidth=1, label="Perfect fit")

    ax.set_xlabel("Predicted diameter (mm)")
    ax.set_ylabel("Actual diameter (mm)")
    ax.set_title(f"Prediction vs actual — holdout split ({version})")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    out_path = PLOT_DIR / version / "prediction_vs_actual_scatter.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_residuals(dataset: pd.DataFrame, version: str = "v1.0") -> Path:
    """Residuals vs predicted values to inspect bias and spread."""
    df = _eval_dataset(dataset)
    df["residual"] = df["actual_next_dia1"] - df["predicted_next_dia1"]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.scatter(df["predicted_next_dia1"], df["residual"], s=20, alpha=0.5, color=SPLIT_COLORS[PLOT_SPLITS[0]])

    ax.set_xlabel("Predicted diameter (mm)")
    ax.set_ylabel("Residual = actual - predicted (mm)")
    ax.set_title(f"Residuals vs predicted values ({version})")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    out_path = PLOT_DIR / version / "residuals_vs_predicted.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_error_by_interval_length(dataset: pd.DataFrame, version: str = "v1.0") -> Path:
    """RMSE by interval length bucket to check whether longer gaps are harder to predict."""
    df = _eval_dataset(dataset)
    df["error"] = df["actual_next_dia1"] - df["predicted_next_dia1"]
    df["error_sq"] = df["error"] ** 2

    bins = [0, 30, 60, 90, 120, 180, np.inf]
    labels = ["0-30", "30-60", "60-90", "90-120", "120-180", "180+"]
    df["interval_bin"] = pd.cut(df["interval_days"], bins=bins, labels=labels, include_lowest=True)

    summary = (
        df.groupby("interval_bin")
        .agg(rmse=("error_sq", lambda s: np.sqrt(s.mean())))
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(summary["interval_bin"], summary["rmse"], color=SPLIT_COLORS[PLOT_SPLITS[0]], alpha=0.85)
    ax.set_xlabel("Interval length (days)")
    ax.set_ylabel("RMSE (mm)")
    ax.set_title(f"RMSE by interval length bucket ({version})")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    out_path = PLOT_DIR / version / "rmse_by_interval_length.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_fleet_monthly_compare(datasets: dict[str, pd.DataFrame]) -> Path:
    """Overlay v1.0 vs v1.1 fleet-monthly predicted diameter on the holdout split."""
    fig, ax = plt.subplots(figsize=(13, 6))

    for version, dataset in datasets.items():
        df = dataset.dropna(subset=["actual_end_dia1", "predicted_next_dia1", "next_interval_end_timestamp"]).copy()
        df = df[df["split"].isin(PLOT_SPLITS)]
        if df.empty:
            continue
        df["next_month"] = df["next_interval_end_timestamp"].dt.to_period("M").dt.to_timestamp()
        predicted_monthly = df.groupby("next_month")["predicted_next_dia1"].mean().sort_index()
        actual_monthly = df.groupby(df["interval_end_timestamp"].dt.to_period("M").dt.to_timestamp())["actual_end_dia1"].mean().sort_index()

        if not actual_monthly.empty:
            ax.plot(actual_monthly.index, actual_monthly.values, color="black",
                    linewidth=2, label=f"Actual — {version}")
        if not predicted_monthly.empty:
            ax.plot(predicted_monthly.index, predicted_monthly.values, color=VERSION_COLORS[version],
                    linewidth=2, linestyle="--", alpha=0.9, label=f"Predicted — {version}")

    ax.set_xlabel("Month")
    ax.set_ylabel("Mean wheel diameter, side 1 (mm)")
    ax.set_title("Fleet-wide mean diameter — v1.0 vs v1.1 predicted-next (holdout split)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.legend(loc="best", fontsize=8, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = PLOT_DIR / "compare" / "diameter_timeseries_fleet_monthly.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_scatter_compare(datasets: dict[str, pd.DataFrame]) -> Path:
    """Overlay v1.0 vs v1.1 predicted-vs-actual on the holdout split."""
    fig, ax = plt.subplots(figsize=(7, 7))

    for version, dataset in datasets.items():
        df = _eval_dataset(dataset)
        ax.scatter(df["predicted_next_dia1"], df["actual_next_dia1"], s=14, alpha=0.4,
                   color=VERSION_COLORS[version], label=version)

    all_vals = []
    for dataset in datasets.values():
        df = _eval_dataset(dataset)
        all_vals += [df["predicted_next_dia1"].min(), df["predicted_next_dia1"].max(),
                     df["actual_next_dia1"].min(), df["actual_next_dia1"].max()]
    min_val, max_val = min(all_vals), max(all_vals)
    ax.plot([min_val, max_val], [min_val, max_val], color="black", linestyle="--", linewidth=1, label="Perfect fit")

    ax.set_xlabel("Predicted diameter (mm)")
    ax.set_ylabel("Actual diameter (mm)")
    ax.set_title("Prediction vs actual — v1.0 vs v1.1 (holdout split)")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    out_path = PLOT_DIR / "compare" / "prediction_vs_actual_scatter.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot actual vs predicted wheel diameter.")
    parser.add_argument("--version", choices=sorted(VERSIONS), default="v1.0",
                        help="Dataset/model version to plot (default: v1.0).")
    parser.add_argument("--compare", action="store_true",
                        help="Also emit v1.0 vs v1.1 overlay plots (fleet-monthly + scatter).")
    args = parser.parse_args()

    datasets: dict[str, pd.DataFrame] = {}
    if args.compare:
        for version in sorted(VERSIONS):
            datasets[version] = load_dataset_with_predictions(version)
        version = "compare"
    else:
        version = args.version
        datasets[version] = load_dataset_with_predictions(version)

    for v, dataset in datasets.items():
        single_path = plot_single_wheelset(dataset, v)
        fleet_path = plot_fleet_monthly_aggregate(dataset, v)
        scatter_path = plot_prediction_scatter(dataset, v)
        residual_path = plot_residuals(dataset, v)
        rmse_path = plot_error_by_interval_length(dataset, v)
        print(f"[{v}] Saved: {single_path}")
        print(f"[{v}] Saved: {fleet_path}")
        print(f"[{v}] Saved: {scatter_path}")
        print(f"[{v}] Saved: {residual_path}")
        print(f"[{v}] Saved: {rmse_path}")

    if args.compare:
        compare_fleet_path = plot_fleet_monthly_compare(datasets)
        compare_scatter_path = plot_scatter_compare(datasets)
        print(f"Saved: {compare_fleet_path}")
        print(f"Saved: {compare_scatter_path}")


if __name__ == "__main__":
    main()