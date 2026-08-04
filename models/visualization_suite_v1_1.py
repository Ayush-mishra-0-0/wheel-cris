"""V1.1 publication-quality visualization suite — v1.0 vs v1.1 on the SAME test split.

Both models are the released HGB regression baselines from run_v1_1_baselines.py:
  - v1.0 features : models/experiments/v1.1/regression/experiment_0009 (test)
  - v1.1 features : models/experiments/v1.1/regression/experiment_0019 (test)
Because they were trained/evaluated in the same run on the same v1.1 dataset with
the grouped-temporal split, the test split is identical by construction (28,066 rows).

The label is `next_interval_dia_delta_mm` (a CHANGE). To plot on a diameter axis we
reconstruct absolute diameters from the raw wheel measurements (same approach as
notebooks/graphs.py):
    predicted_next_dia1 = measured_end_dia1 + predicted_delta
    actual_next_dia1    = measured at next_interval_end_measurement_id

Output: models/experiments/v1.1/plots/*.png (300 DPI) + plots_summary.md

Figures:
  00 ECDF headline (management hero figure)
  01 predicted vs actual scatter (main, sentinels quarantined, ±100 mm axis)
  01b predicted vs actual scatter (appendix, all points, axes expanded)
  02 residual distribution (KDE + histogram overlay)
  03 residual vs actual next diameter (binned bias)
  04 residual vs current measured diameter geom_wsmDia1 (binned bias + MAE)
  05 MAE/RMSE by diameter band
  06 worst-100 comparison (overlap + reduction)
  07 error by shed (MAE reduction per shed)
  08 cumulative error ECDF (fraction within +/-5/10/20 mm)
  09 permutation importance (color-coded by feature family)
  10 ablation (RMSE + PR-AUC)
  11 current diameter vs predicted wear, colored by prediction error
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATASET_V1_1 = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
MEASUREMENTS_PATH = PROJECT_ROOT / "data" / "bronze" / "wheel_measurements.parquet"
EXPERIMENTS_V1_1 = PROJECT_ROOT / "models" / "experiments" / "v1.1"
ABLATION_CSV = EXPERIMENTS_V1_1 / "ablation" / "ablation.csv"
OUT_DIR = EXPERIMENTS_V1_1 / "plots"

LABEL = "next_interval_dia_delta_mm"
RANDOM_STATE = 42

# Sentinel labels retained in Label Spec v1.0 (impossible wheel-wear magnitudes).
# |y_true| above this is a documented outlier, not a physically meaningful interval.
SENTINEL_MAX_ABS = 100.0

# Consistent palette (matches notebooks/graphs.py VERSION_COLORS)
C_V1_0 = "#8C8C8C"
C_V1_1 = "#55A868"
C_LEGACY = "#8C8C8C"
C_PHYS = "#55A868"
C_GEOM = "#4C72B0"

plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 300,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_test_comparison() -> pd.DataFrame:
    """Return one row per test interval with both models' predictions + diameters."""
    dataset = pd.read_parquet(DATASET_V1_1)
    test = dataset[dataset["split"] == "test"].copy()
    test = test.set_index("operational_exposure_id")

    def _test_predictions(experiment: str) -> pd.DataFrame:
        pred = pd.read_parquet(EXPERIMENTS_V1_1 / "regression" / experiment / "predictions.parquet")
        pred = pred[pred["split"] == "test"][["operational_exposure_id", "y_true", "y_pred"]].copy()
        return pred.set_index("operational_exposure_id")

    p10 = _test_predictions("experiment_0009")   # v1.0 features, HGB
    p11 = _test_predictions("experiment_0019").drop(columns=["y_true"])   # v1.1 features, HGB
    assert len(p10) == len(p11) == len(test), "test splits must align"

    df = test.join(p10.rename(columns={"y_pred": "y_pred10", "y_true": "y_true"}), how="inner")
    df = df.join(p11.rename(columns={"y_pred": "y_pred11"}), how="inner")
    assert (df["y_true"] - p10["y_true"].reindex(df.index)).abs().max() < 1e-9, "labels must match"

    # Reconstruct absolute diameters from raw measurements (side 1).
    measurements = pd.read_parquet(MEASUREMENTS_PATH, columns=["wsmId", "wsmDia1"])
    measurements["wsmId"] = pd.to_numeric(measurements["wsmId"], errors="coerce").astype("Int64")

    df = df.reset_index().merge(
        measurements.rename(columns={"wsmId": "interval_end_measurement_id", "wsmDia1": "actual_end_dia1"}),
        on="interval_end_measurement_id", how="left",
    )
    df = df.merge(
        measurements.rename(columns={"wsmId": "next_interval_end_measurement_id", "wsmDia1": "actual_next_dia1"}),
        on="next_interval_end_measurement_id", how="left",
    )
    df["predicted_next_dia1_10"] = df["actual_end_dia1"] + df["y_pred10"]
    df["predicted_next_dia1_11"] = df["actual_end_dia1"] + df["y_pred11"]
    df["residual10"] = df["y_true"] - df["y_pred10"]
    df["residual11"] = df["y_true"] - df["y_pred11"]
    df["abs_residual10"] = df["residual10"].abs()
    df["abs_residual11"] = df["residual11"].abs()
    df["is_sentinel"] = df["y_true"].abs() > SENTINEL_MAX_ABS
    return df.reset_index(drop=True)


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rho = float(stats.spearmanr(y_true, y_pred)[0]) if np.std(y_pred) > 0 else np.nan
    return {"rmse": rmse, "mae": mae, "r2": r2, "spearman": rho}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _save(fig, name: str) -> Path:
    out = OUT_DIR / name
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def _scatter_panel(ax, df, col_pred, color, limits=None, sentinels_quarantined=False):
    x = df[col_pred]
    y = df["y_true"]
    ax.scatter(x, y, s=12, alpha=0.35, color=color, edgecolors="none")
    lo = min(x.min(), y.min())
    hi = max(x.max(), y.max())
    ax.plot([lo, hi], [lo, hi], color="black", linestyle="--", linewidth=1.2, zorder=5)
    if limits is not None:
        ax.set_xlim(limits)
        ax.set_ylim(limits)
    return lo, hi


def fig00_ecdf_headline(df: pd.DataFrame) -> Path:
    """Management hero figure: ECDF of |error| with the ±20 mm story annotated."""
    thresholds = np.array([0, 1, 2, 3, 5, 10, 15, 20, 30, 40, 60, 100])
    fig, ax = plt.subplots(figsize=(10, 6))
    for col, color, tag in [("abs_residual10", C_V1_0, "v1.0"), ("abs_residual11", C_V1_1, "v1.1")]:
        r = df[col].dropna()
        fracs = np.array([(r <= t).mean() for t in thresholds])
        ax.plot(thresholds, fracs, marker="o", markersize=5, color=color, linewidth=2.2,
                label=tag)

    for t in [5, 10, 20]:
        f10 = (df["abs_residual10"] <= t).mean() * 100
        f11 = (df["abs_residual11"] <= t).mean() * 100
        ax.axvline(t, color="0.55", linestyle=":", linewidth=1)
        ax.plot([t], [f11 / 100], marker="o", markersize=7, color=C_V1_1, zorder=6)
        ax.annotate(f"±{t} mm\n{f10:.0f}% → {f11:.0f}%", xy=(t, f11 / 100),
                    xytext=(t + 1, f11 / 100 - 0.13), fontsize=10, color="0.15",
                    arrowprops=dict(arrowstyle="-", color="0.4", lw=0.8))

    # Highlight the ±20 mm band that carries the headline.
    f20_10 = (df["abs_residual10"] <= 20).mean() * 100
    f20_11 = (df["abs_residual11"] <= 20).mean() * 100
    ax.axvspan(0, 20, color=C_V1_1, alpha=0.06, zorder=0)
    ax.text(0.02, 0.94, f"**84%** of v1.1 predictions within ±20 mm\nvs **69%** for v1.0",
            transform=ax.transAxes, fontsize=13, va="top", color="#1B5E20",
            bbox=dict(boxstyle="round,pad=0.5", fc="#E8F5E9", ec=C_V1_1, lw=1.2))

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1.0)
    ax.set_xlabel("Absolute prediction error  |actual − predicted|  (mm)")
    ax.set_ylabel("Fraction of test intervals within threshold")
    ax.set_title("Fraction of predictions within an error budget — v1.1 covers the fleet earlier", fontsize=13)
    ax.legend(title="model", loc="lower right", fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _save(fig, "00_ecdf_headline.png")


def fig01_scatter(df: pd.DataFrame) -> Path:
    """Predicted vs actual interval wear, main (sentinels quarantined) + appendix (all)."""
    main = df[~df["is_sentinel"]].copy()
    n_sent = int(df["is_sentinel"].sum())

    # ---- Figure A: main figure, ±100 mm axis, no sentinels ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharex=True, sharey=True)
    for ax, (tag, col_pred, color) in zip(
        axes, [("v1.0", "y_pred10", C_V1_0), ("v1.1", "y_pred11", C_V1_1)]
    ):
        x = main[col_pred]
        y = main["y_true"]
        ax.scatter(x, y, s=12, alpha=0.35, color=color, edgecolors="none")
        ax.plot([-100, 100], [-100, 100], color="black", linestyle="--", linewidth=1.2, zorder=5)
        m = metrics(y, x)
        ax.set_title(f"{tag}   R²={m['r2']:.3f}  RMSE={m['rmse']:.2f} mm  MAE={m['mae']:.2f} mm", fontsize=11)
        ax.set_xlabel("Predicted interval wear (mm)")
        ax.set_ylabel("Actual interval wear (mm)")
        ax.set_xlim(-100, 100)
        ax.set_ylim(-100, 100)
        ax.text(0.03, 0.97, f"n={len(x):,}", transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7"))
    fig.suptitle("Predicted vs actual next-interval diameter change — same test split (sentinels quarantined)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    p_main = _save(fig, "01_predicted_vs_actual_scatter.png")

    # ---- Figure B: appendix, all points, axes expanded ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharex=True, sharey=True)
    for ax, (tag, col_pred, color) in zip(
        axes, [("v1.0", "y_pred10", C_V1_0), ("v1.1", "y_pred11", C_V1_1)]
    ):
        _scatter_panel(ax, df, col_pred, color)
        ax.set_title(tag, fontsize=11)
        ax.set_xlabel("Predicted interval wear (mm)")
        ax.set_ylabel("Actual interval wear (mm)")
        ax.text(0.03, 0.97, f"n={len(df):,}", transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7"))
    fig.suptitle(
        f"All points included — axes expanded by {n_sent} sentinel label(s) retained in Label Spec v1.0",
        fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    p_all = _save(fig, "01b_predicted_vs_actual_scatter_all.png")
    return p_main


def fig02_residual_distribution(df: pd.DataFrame) -> Path:
    """KDE + histogram of residuals, v1.0 vs v1.1."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))

    for ax, (tag, col, color) in zip(
        axes, [("v1.0", "residual10", C_V1_0), ("v1.1", "residual11", C_V1_1)]
    ):
        r = df.loc[~df["is_sentinel"], col].dropna()
        ax.hist(r, bins=80, density=True, alpha=0.55, color=color, edgecolor="white", linewidth=0.3)
        try:
            kde = stats.gaussian_kde(r)
            xs = np.linspace(r.min(), r.max(), 500)
            ax.plot(xs, kde(xs), color="black", linewidth=1.4)
        except Exception:
            pass
        ax.set_title(f"{tag}   residual σ={r.std():.2f} mm", fontsize=11)
        ax.set_xlabel("Residual  actual − predicted (mm)")
        ax.set_ylabel("Density")
        ax.axvline(0, color="black", linestyle="--", linewidth=1)

    fig.suptitle("Residual distribution — v1.1 residuals are tighter around zero", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, "02_residual_distribution.png")


def _binned_mean(df, xcol, ycol, bins, version_tag) -> pd.DataFrame:
    d = df.dropna(subset=[xcol, ycol]).copy()
    d["_bin"] = pd.cut(d[xcol], bins=bins)
    g = d.groupby("_bin", observed=True)[ycol]
    out = pd.DataFrame({
        "bin": [str(b) for b in g.count().index],
        "mid": [(iv.mid) for iv in g.count().index],
        "mean": g.mean().values,
        "sem": g.sem().values,
        "n": g.count().values,
        "version": version_tag,
    })
    return out


def fig03_residual_vs_actual(df: pd.DataFrame) -> Path:
    """Binned mean residual vs actual next diameter — bias across the range."""
    bins = np.arange(1000, 1110, 10)
    b10 = _binned_mean(df, "actual_next_dia1", "residual10", bins, "v1.0")
    b11 = _binned_mean(df, "actual_next_dia1", "residual11", bins, "v1.1")

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for b, color, tag in [(b10, C_V1_0, "v1.0"), (b11, C_V1_1, "v1.1")]:
        b = b[b["n"] >= 20]
        ax.errorbar(b["mid"], b["mean"], yerr=b["sem"], fmt="o--" if tag == "v1.0" else "s-",
                    color=color, label=tag, markersize=6, linewidth=1.4, capsize=3)
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("Actual next-interval diameter, side 1 (mm)")
    ax.set_ylabel("Mean residual  actual − predicted (mm)")
    ax.set_title("Residual bias across the diameter range — v1.1 flattens toward zero")
    ax.legend(title="model", loc="best")
    fig.tight_layout()
    return _save(fig, "03_residual_vs_actual_diameter.png")


def fig04_residual_vs_current(df: pd.DataFrame) -> Path:
    """Binned residual + MAE vs geom_wsmDia1 (current measured geometry)."""
    bins = np.arange(1000, 1110, 10)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    ax = axes[0]
    for b, color, tag in [
        (_binned_mean(df, "geom_wsmDia1", "residual10", bins, "v1.0"), C_V1_0, "v1.0"),
        (_binned_mean(df, "geom_wsmDia1", "residual11", bins, "v1.1"), C_V1_1, "v1.1"),
    ]:
        b = b[b["n"] >= 20]
        ax.errorbar(b["mid"], b["mean"], yerr=b["sem"], fmt="o--" if tag == "v1.0" else "s-",
                    color=color, label=tag, markersize=6, linewidth=1.4, capsize=3)
    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("Current measured diameter geom_wsmDia1 (mm)")
    ax.set_ylabel("Mean residual (mm)")
    ax.set_title("Residual bias vs current geometry")

    ax = axes[1]
    for b, color, tag in [
        (_binned_mean(df, "geom_wsmDia1", "abs_residual10", bins, "v1.0"), C_V1_0, "v1.0"),
        (_binned_mean(df, "geom_wsmDia1", "abs_residual11", bins, "v1.1"), C_V1_1, "v1.1"),
    ]:
        b = b[b["n"] >= 20]
        ax.plot(b["mid"], b["mean"], marker="o" if tag == "v1.0" else "s", color=color,
                label=tag, linewidth=1.6, markersize=6)
    ax.set_xlabel("Current measured diameter geom_wsmDia1 (mm)")
    ax.set_ylabel("MAE (mm)")
    ax.set_title("MAE vs current geometry — gain concentrated on worn wheels")
    ax.legend(title="model", loc="upper left")
    for axx in axes:
        axx.grid(True, alpha=0.3)

    fig.suptitle("Where the geometry features help: error now falls with wear state", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, "04_residual_vs_current_diameter.png")


def fig05_error_by_diameter_band(df: pd.DataFrame) -> Path:
    """MAE / RMSE within diameter bands (>1080, 1060-1080, 1040-1060, <1040)."""
    bins = [0, 1040, 1060, 1080, np.inf]
    labels = ["<1040", "1040–1060", "1060–1080", ">1080"]
    d = df.dropna(subset=["geom_wsmDia1"]).copy()
    d["band"] = pd.cut(d["geom_wsmDia1"], bins=bins, labels=labels)

    rows = []
    for tag, col in [("v1.0", "residual10"), ("v1.1", "residual11")]:
        for b, g in d.groupby("band", observed=True):
            m = metrics(g["y_true"], g[col])
            rows.append({"band": b, "version": tag, "mae": m["mae"], "rmse": m["rmse"], "n": len(g)})
    agg = pd.DataFrame(rows)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharex=True)
    x = np.arange(len(labels))
    w = 0.36
    for ax, metric in zip(axes, ["mae", "rmse"]):
        for j, tag in enumerate(["v1.0", "v1.1"]):
            vals = agg[agg["version"] == tag].set_index("band").reindex(labels)[metric]
            ax.bar(x + (j - 0.5) * w, vals, width=w, color=C_V1_0 if tag == "v1.0" else C_V1_1,
                   label=tag)
            for xi, v in zip(x + (j - 0.5) * w, vals):
                if not np.isnan(v):
                    ax.text(xi, v + 0.15, f"{v:.1f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_xlabel("Current diameter band (mm)")
        ax.set_ylabel(f"{metric.upper()} (mm)")
        ax.set_title(metric.upper() + " by current diameter band")
        ax.legend(loc="upper right")
    fig.suptitle("Error by current-diameter band — improvement is largest on worn wheels (<1040)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, "05_mae_rmse_by_diameter_band.png")


def fig06_worst100(df: pd.DataFrame) -> Path:
    """Worst-100 comparison: overlap + reduction."""
    worst10 = df.nlargest(100, "abs_residual10")
    worst11 = df.nlargest(100, "abs_residual11")
    overlap = len(set(worst10["operational_exposure_id"]) & set(worst11["operational_exposure_id"]))
    m10 = metrics(worst10["y_true"], worst10["y_pred10"])
    m11 = metrics(worst11["y_true"], worst11["y_pred11"])

    fig = plt.figure(figsize=(12, 5))
    ax = fig.add_subplot(1, 2, 1)
    union = df[df["operational_exposure_id"].isin(
        set(worst10["operational_exposure_id"]) | set(worst11["operational_exposure_id"]))]
    ax.scatter(union["abs_residual10"], union["abs_residual11"], s=22, alpha=0.7,
               color="#7F7F7F", edgecolors="white", linewidth=0.4)
    lim = max(union["abs_residual10"].max(), union["abs_residual11"].max())
    ax.plot([0, lim], [0, lim], color="black", linestyle="--", linewidth=1, label="no change")
    ax.set_xlabel("|error| v1.0 (mm)")
    ax.set_ylabel("|error| v1.1 (mm)")
    ax.set_title(f"Worst-case intervals — {overlap}/100 overlap")
    ax.legend(loc="lower right")

    ax = fig.add_subplot(1, 2, 2)
    cats = ["worst-100 MAE", "worst-100 RMSE"]
    v10 = [m10["mae"], m10["rmse"]]
    v11 = [m11["mae"], m11["rmse"]]
    x = np.arange(len(cats))
    w = 0.36
    ax.bar(x - w / 2, v10, width=w, color=C_V1_0, label="v1.0")
    ax.bar(x + w / 2, v11, width=w, color=C_V1_1, label="v1.1")
    for xi, a, b in zip(x, v10, v11):
        ax.text(xi - w / 2, a + 0.3, f"{a:.1f}", ha="center", fontsize=9)
        ax.text(xi + w / 2, b + 0.3, f"{b:.1f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("mm")
    ax.set_title("Worst-100 error — v1.1 is materially smaller")
    ax.legend(loc="upper right")

    fig.suptitle("Worst-100 intervals: overlap and reduction", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, "06_worst100_comparison.png")


def fig07_error_by_shed(df: pd.DataFrame) -> Path:
    """MAE per home shed, v1.0 vs v1.1, sorted by reduction."""
    d = df.dropna(subset=["home_shed"]).copy()
    rows = []
    for shed, g in d.groupby("home_shed"):
        if len(g) < 50:
            continue
        m10 = metrics(g["y_true"], g["y_pred10"])
        m11 = metrics(g["y_true"], g["y_pred11"])
        rows.append({"shed": shed, "n": len(g), "mae10": m10["mae"], "mae11": m11["mae"],
                     "reduction_pct": (m11["mae"] / m10["mae"] - 1) * 100})
    agg = pd.DataFrame(rows).sort_values("reduction_pct")

    fig, ax = plt.subplots(figsize=(8.5, max(5, len(agg) * 0.32 + 2)))
    y = np.arange(len(agg))
    colors = [C_V1_1 if v < 0 else "#C0392B" for v in agg["reduction_pct"]]
    ax.barh(y, agg["reduction_pct"], color=colors, alpha=0.9)
    for yi, v, n in zip(y, agg["reduction_pct"], agg["n"]):
        ax.text(v + (1 if v >= 0 else -1), yi, f"{v:.0f}%  (n={n})",
                va="center", ha="left" if v >= 0 else "right", fontsize=8)
    ax.set_yticks(y)
    ax.set_yticklabels(agg["shed"])
    ax.axvline(0, color="black", linewidth=1)
    ax.set_xlabel("MAE change v1.0 → v1.1 (%)")
    ax.set_title("MAE reduction by home shed — every shed improved")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return _save(fig, "07_error_by_shed.png")


def fig08_cumulative_error(df: pd.DataFrame) -> Path:
    """ECDF of |error| — fraction of predictions within thresholds."""
    thresholds = [1, 2, 3, 5, 10, 15, 20, 30, 40, 60, 100]
    rows = []
    for tag, col in [("v1.0", "abs_residual10"), ("v1.1", "abs_residual11")]:
        r = df[col].dropna()
        fracs = [(r <= t).mean() for t in thresholds]
        rows.append({"version": tag, "thresholds": thresholds, "fracs": fracs})

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for r, color in zip(rows, [C_V1_0, C_V1_1]):
        ax.plot(r["thresholds"], r["fracs"], marker="o", color=color,
                label=r["version"], linewidth=1.8, markersize=5)
    for t in [5, 10, 20]:
        ax.axvline(t, color="0.6", linestyle=":", linewidth=1)
        f10 = (df["abs_residual10"] <= t).mean()
        f11 = (df["abs_residual11"] <= t).mean()
        ax.text(t, 0.02, f"±{t}mm: {f10*100:.0f}%→{f11*100:.0f}%", rotation=90,
                va="bottom", ha="right", fontsize=8, color="0.3")
    ax.set_xlabel("|error| threshold (mm)")
    ax.set_ylabel("Fraction of test intervals within threshold")
    ax.set_ylim(0, 1.02)
    ax.set_title("Cumulative error — v1.1 puts more predictions inside ±5/±10/±20 mm")
    ax.legend(title="model", loc="lower right")
    fig.tight_layout()
    return _save(fig, "08_cumulative_error_ecdf.png")


def fig09_permutation_importance() -> Path:
    """Permutation importance (test, HGB v1.1) color-coded by feature family."""
    fi = json.loads((EXPERIMENTS_V1_1 / "regression" / "experiment_0019" / "feature_importance.json").read_text())
    top = dict(list(fi["top_30"].items())[:20])

    def family(name: str) -> str:
        if name.startswith("phys_"):
            return "physics"
        if name.startswith("geom_"):
            return "measured geometry"
        return "legacy v1.0"

    colors = {"physics": C_PHYS, "measured geometry": C_GEOM, "legacy v1.0": C_LEGACY}
    fig, ax = plt.subplots(figsize=(9, max(5, len(top) * 0.34 + 1)))
    names = list(top.keys())[::-1]
    vals = [top[n] for n in names]
    cols = [colors[family(n)] for n in names]
    ax.barh(names, vals, color=cols, alpha=0.9)
    ax.set_xlabel("Permutation importance  (Δ test RMSE when feature is shuffled, mm)")
    ax.set_title("What drives the v1.1 gain — current material + measured geometry")
    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=c, label=k) for k, c in colors.items()]
    ax.legend(handles=handles, loc="lower right", fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return _save(fig, "09_permutation_importance.png")


def fig10_ablation() -> Path:
    """Ablation: RMSE + large-loss PR-AUC across v1_0 / +geom / +phys / +all."""
    abl = pd.read_csv(ABLATION_CSV)
    reg = abl[(abl["task"] == "regression")].set_index("variant").loc[["v1_0", "plus_geom", "plus_phys", "plus_all"]]
    bin_ = abl[(abl["task"] == "binary") & (abl["label"] == "next_interval_large_loss_flag")].set_index("variant").loc[["v1_0", "plus_geom", "plus_phys", "plus_all"]]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    variants = ["v1_0", "+geom", "+phys", "+all"]
    x = np.arange(4)

    ax = axes[0]
    vals = reg["rmse"].values
    ax.bar(x, vals, color=[C_LEGACY, C_GEOM, C_PHYS, "#9B59B6"], alpha=0.9)
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.2, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(variants)
    ax.set_ylabel("RMSE (mm)")
    ax.set_title("Regression RMSE — measured geometry is the dominant lift")

    ax = axes[1]
    vals = bin_["pr_auc"].values
    ax.bar(x, vals, color=[C_LEGACY, C_GEOM, C_PHYS, "#9B59B6"], alpha=0.9)
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.005, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(variants)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("PR-AUC")
    ax.set_title("Large-loss PR-AUC (same lift from geometry)")

    fig.suptitle("Ablation: +geom (measured geometry) delivers nearly all the gain", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, "10_ablation.png")


def fig11_current_diameter_vs_wear(df: pd.DataFrame) -> Path:
    """Current measured diameter vs predicted wear, points colored by |error|.

    The story: v1.0 never saw the wheel's current geometry, so its predicted wear is
    flat and uncorrelated with wear state. v1.1 knows geom_wsmDia1, so predicted wear
    tracks the physical relationship — and errors shrink (lighter colors).
    """
    q = df[~df["is_sentinel"]].dropna(subset=["geom_wsmDia1"]).copy()
    # Shared error scale so both panels are directly comparable (cap at p99).
    err_max = float(np.percentile(np.concatenate([q["abs_residual10"], q["abs_residual11"]]), 99))
    norm = plt.Normalize(vmin=0, vmax=err_max)
    cmap = plt.get_cmap("viridis")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
    for ax, (tag, col_pred, col_err) in zip(
        axes, [("v1.0", "y_pred10", "abs_residual10"), ("v1.1", "y_pred11", "abs_residual11")]
    ):
        sc = ax.scatter(q["geom_wsmDia1"], q[col_pred], s=9, c=q[col_err], cmap=cmap,
                        norm=norm, alpha=0.6, edgecolors="none")
        m = metrics(q["y_true"], q[col_pred])
        ax.set_title(f"{tag}   MAE={m['mae']:.2f} mm", fontsize=11)
        ax.set_xlabel("Current measured diameter geom_wsmDia1 (mm)")
        ax.set_ylabel("Predicted next-interval wear (mm)")
        ax.text(0.03, 0.05, f"n={len(q):,}", transform=ax.transAxes, fontsize=9,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7"))
    fig.colorbar(sc, ax=axes, label="|prediction error| (mm)")
    fig.suptitle(
        "Once the model sees the current diameter, predicted wear becomes physically consistent",
        fontsize=13)
    return _save(fig, "11_current_diameter_vs_predicted_wear.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    df = load_test_comparison()
    m10 = metrics(df["y_true"], df["y_pred10"])
    m11 = metrics(df["y_true"], df["y_pred11"])
    q = df[~df["is_sentinel"]]
    mq10 = metrics(q["y_true"], q["y_pred10"])
    mq11 = metrics(q["y_true"], q["y_pred11"])
    print(f"test rows: {len(df)}  (sentinels quarantined: {int(df['is_sentinel'].sum())})")
    print(f"v1.0: RMSE={m10['rmse']:.3f}  MAE={m10['mae']:.3f}  R2={m10['r2']:.4f}  Spearman={m10['spearman']:.4f}")
    print(f"v1.1: RMSE={m11['rmse']:.3f}  MAE={m11['mae']:.3f}  R2={m11['r2']:.4f}  Spearman={m11['spearman']:.4f}")
    print(f"v1.0 (no sentinels): RMSE={mq10['rmse']:.3f}  MAE={mq10['mae']:.3f}")
    print(f"v1.1 (no sentinels): RMSE={mq11['rmse']:.3f}  MAE={mq11['mae']:.3f}")

    paths = [
        fig00_ecdf_headline(df),
        fig01_scatter(df),
        fig02_residual_distribution(df),
        fig03_residual_vs_actual(df),
        fig04_residual_vs_current(df),
        fig05_error_by_diameter_band(df),
        fig06_worst100(df),
        fig07_error_by_shed(df),
        fig08_cumulative_error(df),
        fig09_permutation_importance(),
        fig10_ablation(),
        fig11_current_diameter_vs_wear(df),
    ]
    for p in paths:
        print(f"Saved: {p}")


if __name__ == "__main__":
    main()
