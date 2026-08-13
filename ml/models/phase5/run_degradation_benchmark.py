"""Phase 5 Layer 2 - degradation-prediction benchmark (root/flange/tread/dia wear).

Predicts future wear levels at horizons 30/90/180d from a point-in-time anchor
(the frozen v5 degradation substrate). Targets are within-segment horizon
states (contract v1.2 section 4); train labels only count when their target
measurement time is knowable at the deployment cutoff.

Models per (target dim, horizon):
  B0  persistence        = current wear (no degradation assumed, delta = 0)
  B1  linear            = trailing-90d per-day rate * H
  B2  ridge             = ridge regression on imputed numeric set
  C1  XGBRegressor      = gradient boosting (native NaN)

TARGET_MODE = "delta": every model regresses the CHANGE (delta = tgt - anchor) and
predictions are reconstructed as anchor + delta for evaluation. This removes
between-wheel LEVEL dominance (the old level-regression pitfall where R2 came
almost entirely from wsmFla level variance, not trend) while keeping MAE/RMSE/R2/
Spearman in the SAME mm units, so before/after numbers are directly comparable.

Static grid: all 4 dims x 3 horizons, temporal PIT train/test split.
Rolling headliner: quarterly cutoffs over the test window (label known at T),
reports median/IQR across cutoffs - never best-cutoff.

Metrics (regression): MAE, RMSE, R2, Spearman. Risk-ranking framing:
capture@k = share of total actual future-wear mass found in the top-k
predicted rows (concentration; >k means the model ranks hot wheels up).

Output: models/experiments/v5/degradation_benchmark.json + plots + report md.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
OUT = ROOT / "models" / "experiments" / "v5"

TARGET_MODE = "delta"
HORIZONS = (30, 90, 180)
TARGET_DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
SEED = 42
ROLL_STEP = 90

RATE_COL = {
    "wsmRoot": "wsmRoot_rate_per_day_90d",
    "wsmDia": "wsmDia_rate_per_day_90d",
    "wsmFlange": "ph5_wsmFlange_rate_per_day_90d",
    "wsmThread": "ph5_wsmThread_rate_per_day_90d",
}

NUM_FEATS = [
    "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
    "mean_wsmFlangeThickness", "mean_wsmWheelGauge",
    "ph5_wsmFlange_rate_per_day_30d", "ph5_wsmFlange_rate_per_day_90d",
    "ph5_wsmFlange_rate_per_day_180d",
    "ph5_wsmThread_rate_per_day_30d", "ph5_wsmThread_rate_per_day_90d",
    "ph5_wsmThread_rate_per_day_180d",
    "wsmRoot_rate_per_day_30d", "wsmRoot_rate_per_day_90d",
    "wsmDia_rate_per_day_30d", "wsmDia_rate_per_day_90d",
    "days_since_turning", "distance_since_turning_km",
    "days_since_last_inspection", "wheel_age_days_proxy",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d", "inspection_count_180d",
    "km_last_30d", "km_last_90d", "km_last_180d",
    "rtis_reporting_coverage_pct", "distance_per_day_km",
    "n_prior_turns", "segment_index",
    "axle_position_1_6", "wheel_position_1_12", "wheel_profile_2class",
]
CAT_FEATS = ["LocoType", "home_shed", "defect_zone", "shed_any"]


def build_matrix(df, enc=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(cat)
    else:
        Xc = enc.transform(cat)
    return Xn, Xc, enc


def metrics(y, yh):
    y = np.asarray(y, float)
    yh = np.asarray(yh, float)
    ok = np.isfinite(y) & np.isfinite(yh)
    y, yh = y[ok], yh[ok]
    if len(y) < 10:
        return None
    mae = float(np.mean(np.abs(y - yh)))
    rmse = float(np.sqrt(np.mean((y - yh) ** 2)))
    ss = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = float(1.0 - np.sum((y - yh) ** 2) / ss)
    try:
        sr = spearmanr(y, yh)
        rho = float(getattr(sr, "statistic", sr[0]))
    except Exception:
        rho = None
    return {"mae": mae, "rmse": rmse, "r2": r2, "spearman": rho, "n": int(len(y))}


def capture_at(y, yh, k_frac):
    y = np.asarray(y, float)
    yh = np.asarray(yh, float)
    ok = np.isfinite(y) & np.isfinite(yh)
    y, yh = y[ok], yh[ok]
    n = len(y)
    if n < 20:
        return None
    k = max(1, min(int(np.floor(k_frac * n)), n))
    top = np.argsort(-yh, kind="mergesort")[:k]
    tot = y.sum()
    if tot <= 0:
        return None
    return round(float(y[top].sum() / tot), 4)


def main() -> None:
    df = pd.read_parquet(DATA)
    t = pd.to_datetime(df["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    tgt_arr = {H: pd.to_datetime(df[f"tgt_obs_ts_{H}d"]).to_numpy(dtype="datetime64[us]")
               for H in HORIZONS}
    is_train = df["split"].eq("train").to_numpy()
    train_cutoff = pd.to_datetime(df.loc[is_train, "measurement_timestamp"]).max()
    t_te = t_arr[~is_train]

    Xn_all, Xc_all, cat_enc = build_matrix(df)

    summary = {"task": "phase 5 layer 2 degradation benchmark",
               "contract": "wheel_profile_lifecycle_contract_v1",
               "source": str(DATA.relative_to(ROOT)),
               "target_mode": TARGET_MODE,
               "models": ["B0_persistence", "B1_linear", "B2_ridge", "C1_xgb"],
               "static": {}, "rolling": {}}

    def predict(name, tr, te, dim, H):
        # delta target (TARGET_MODE): y = tgt - anchor; predictions reconstructed
        # as level = anchor + delta so metrics stay in mm and remain comparable.
        # Returns (level_pred, delta_pred) so both spaces can be scored.
        cur_tr = df.loc[tr, f"mean_{dim}"].to_numpy(dtype=float)
        cur_te = df.loc[te, f"mean_{dim}"].to_numpy(dtype=float)
        ytr = df.loc[tr, f"tgt_{dim}_{H}d"].to_numpy(dtype=float) - cur_tr
        if name == "B0_persistence":
            delta_te = np.zeros(int(te.sum()))
        elif name == "B1_linear":
            rate = df.loc[te, RATE_COL[dim]].to_numpy(dtype=float)
            delta_te = np.where(np.isfinite(rate), rate * H, 0.0)
        elif name == "B2_ridge":
            Xit = np.hstack([Xn_all[tr], Xc_all[tr]])
            imp = SimpleImputer().fit(Xit)
            m = Ridge(alpha=1.0, random_state=SEED).fit(imp.transform(Xit), ytr)
            delta_te = m.predict(imp.transform(np.hstack([Xn_all[te], Xc_all[te]])))
        elif name == "C1_xgb":
            Xt = np.hstack([Xn_all[tr], Xc_all[tr]])
            m = XGBRegressor(n_estimators=400, learning_rate=0.08, max_depth=6,
                             subsample=0.85, colsample_bytree=0.85,
                             tree_method="hist", random_state=SEED, verbosity=0)
            m = m.fit(Xt, ytr)
            delta_te = m.predict(np.hstack([Xn_all[te], Xc_all[te]]))
        else:
            raise ValueError(name)
        return cur_te + delta_te, delta_te

    # ---------- static grid ----------
    for dim in TARGET_DIMS:
        summary["static"][dim] = {}
        for H in HORIZONS:
            elig = df[f"eligible_{dim}_{H}d"].to_numpy()
            tgt_obs = tgt_arr[H]
            ycol = df[f"tgt_{dim}_{H}d"].to_numpy(dtype=float)
            cur = df[f"mean_{dim}"].to_numpy(dtype=float)
            yok = np.isfinite(ycol) & np.isfinite(cur)
            tr = is_train & elig & yok & (tgt_obs <= train_cutoff)
            te = (~is_train) & elig & yok
            yte = ycol[te]
            cur_te = df.loc[te, f"mean_{dim}"].to_numpy(dtype=float)
            dte = yte - cur_te
            per_model = {}
            for name in summary["models"]:
                yh, dh = predict(name, tr, te, dim, H)
                per_model[name] = {**metrics(yte, yh),
                                   **{"delta_" + k: v for k, v in metrics(dte, dh).items()
                                      if k != "n"},
                                   "capture05": capture_at(yte, yh, 0.05),
                                   "capture10": capture_at(yte, yh, 0.10)}
            summary["static"][dim][f"{H}d"] = {
                "n_train": int(tr.sum()), "n_test": int(te.sum()),
                "models": per_model}
            print(f"static {dim} {H}d  train={tr.sum():,} test={te.sum():,}")

    # ---------- rolling headliner (root/flange, H=90, quarterly refit) ----------
    H = 90
    cutoffs = pd.date_range(start=t_te.min(), end=t_te.max(), freq=f"{ROLL_STEP}D")
    for dim in ("wsmRoot", "wsmFlange"):
        elig = df[f"eligible_{dim}_{H}d"].to_numpy()
        tgt_obs = tgt_arr[H]
        ycol = df[f"tgt_{dim}_{H}d"].to_numpy(dtype=float)
        cur = df[f"mean_{dim}"].to_numpy(dtype=float)
        yok = np.isfinite(ycol) & np.isfinite(cur)
        per_cut = []
        for T in cutoffs:
            Tn = np.datetime64(T, "us")
            known = tgt_obs <= Tn
            tr = (t_arr < Tn) & known & elig & yok
            te = (t_arr > Tn - np.timedelta64(ROLL_STEP, "D")) & \
                (t_arr <= Tn) & known & elig & yok
            if int(tr.sum()) < 5000 or int(te.sum()) < 300:
                continue
            yte = ycol[te]
            cur_te = df.loc[te, f"mean_{dim}"].to_numpy(dtype=float)
            dte = yte - cur_te
            res = {"cutoff": str(T.date()), "n_test": int(te.sum())}
            for name in summary["models"]:
                yh, dh = predict(name, tr, te, dim, H)
                res[name] = metrics(yte, yh)
                res[name]["delta_mae"] = metrics(dte, dh)["mae"]
                res[name]["delta_r2"] = metrics(dte, dh)["r2"]
            per_cut.append(res)
            print(f"roll {dim} {T.date()} train={tr.sum():,} test={te.sum():,}")
        if per_cut:
            ag = {}
            for name in summary["models"]:
                maes = [c[name]["mae"] for c in per_cut if c.get(name)]
                r2s = [c[name]["r2"] for c in per_cut if c.get(name)]
                ag[name] = {
                    "mae_median": round(float(np.median(maes)), 4) if maes else None,
                    "mae_iqr": round(float(np.percentile(maes, 75) - np.percentile(maes, 25)), 4) if maes else None,
                    "r2_median": round(float(np.median(r2s)), 4) if r2s else None,
                    "n_cutoffs": len(per_cut),
                }
            summary["rolling"][dim] = {"per_cutoff": per_cut, "aggregate": ag}

    # ---------- plots ----------
    OUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for ax, dim in zip(axes, ["wsmRoot", "wsmFlange", "wsmThread"]):
        row = summary["static"][dim]["90d"]["models"]
        names = list(row)
        maes = [row[n]["mae"] for n in names]
        r2s = [row[n]["r2"] for n in names]
        x = np.arange(len(names))
        ax.bar(x, maes, 0.5, color="#5499c7")
        ax.set_xticks(x); ax.set_xticklabels([n.split("_")[0] for n in names])
        ax.set_ylabel("MAE (mm)"); ax.set_title(f"{dim} @90d")
        ax2 = ax.twinx()
        ax2.plot(x, r2s, "o", color="#e74c3c")
        ax2.set_ylabel("R2", color="#e74c3c")
        ax.grid(alpha=0.3)
    fig.suptitle("Layer 2 degradation - MAE/R2 by model (static temporal grid)")
    fig.tight_layout(); fig.savefig(OUT / "degradation_mae_r2.png", dpi=130)
    plt.close(fig)

    dim, H = "wsmRoot", 90
    elig = df[f"eligible_{dim}_{H}d"].to_numpy()
    ycol_s = df[f"tgt_{dim}_{H}d"].to_numpy(dtype=float)
    yok_s = np.isfinite(ycol_s) & np.isfinite(df[f"mean_{dim}"].to_numpy(dtype=float))
    tr = is_train & elig & yok_s & (tgt_arr[H] <= train_cutoff)
    te = (~is_train) & elig & yok_s
    yte = ycol_s[te]
    cur_te = df.loc[te, f"mean_{dim}"].to_numpy(dtype=float)
    yh, _ = predict("C1_xgb", tr, te, dim, H)
    fig, ax = plt.subplots(figsize=(6, 6))
    ok = np.isfinite(yte) & np.isfinite(yh)
    ax.scatter(yte[ok], yh[ok], s=4, alpha=0.12)
    lim = [0, max(float(np.nanmax(yte[ok])), float(np.nanmax(yh[ok])))]
    ax.plot(lim, lim, "r--", lw=1.2)
    ax.set_xlabel("actual"); ax.set_ylabel("predicted (C1)")
    ax.set_title(f"C1 root @90d (n={int(te.sum()):,})")
    fig.tight_layout(); fig.savefig(OUT / "degradation_c1_scatter_root90.png", dpi=130)
    plt.close(fig)

    (OUT / "degradation_benchmark.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    main()