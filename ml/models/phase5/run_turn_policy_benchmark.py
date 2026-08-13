"""Phase 5 Layer 3 - turning/profile-policy benchmark (B-A cut model).

Target: the machining action and post-turn state given pre-turn context:
  post-turn diameter = pre_dia - cut, where cut (~ B - A) is learned as
  f(pre_turn_state, shed policy, profile class, position, prior-turn history).

Models:
  B0_global    cut = global train median (single historical machining norm)
  B1_shed    cut = per-shed train median (recovered per-shed "B - A" policy;
               lookups are train-only / PIT, unseen sheds fall back to B0)
  B2_ridge    ridge regression on pre-state + ordinal categorical context
  C1_xgb     XGBRegressor on the same context (native NaN)

Evaluation (regression on cut_dia and each post-turn dim):
  MAE, RMSE, R2, Spearman; MAE implied post-turn diameter error is identical
  to cut MAE (post_dia = pre_dia - cut exact in our events).

Temporal PIT split: train = pre_ts < 2024-08-12; test = on/after. Shed-policy
baseline computed strictly on train. Also prints the recovered per-shed policy
table (median cut by shed) = Layer-1 "B - A" recovery, machine-readable.

Output: models/experiments/v5/turn_policy_benchmark.json + plots + report md.
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
DATA = ROOT / "model_datasets" / "v5" / "turn_policy_benchmark.parquet"
OUT = ROOT / "models" / "experiments" / "v5"

NUM_FEATS = ["pre_wsmDia", "pre_wsmFlange", "pre_wsmRoot", "pre_wsmThread",
             "days_between", "segment_index", "month"]
CAT_FEATS = ["shed_any", "wheel_profile_2class", "wheel_position_1_12"]
POST_DIMS = {"cut_dia": "cut (mm)", "post_wsmDia": "post dia (mm)",
             "post_wsmFlange": "post flange (mm)",
             "post_wsmRoot": "post root (mm)",
             "post_wsmThread": "post thread (mm)"}
SEED = 42
MIN_SHED_EVENTS = 10


def metrics(y, yh):
    y = np.asarray(y, float)
    yh = np.asarray(yh, float)
    ok = np.isfinite(y) & np.isfinite(yh)
    if ok.sum() < 10:
        return None
    y, yh = y[ok], yh[ok]
    mae = float(np.mean(np.abs(y - yh)))
    rmse = float(np.sqrt(np.mean((y - yh) ** 2)))
    ss = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = float(1.0 - np.sum((y - yh) ** 2) / ss)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rho, p = spearmanr(y, yh)
        rho = float(rho)
    except Exception:
        rho = None
    return {"mae": mae, "rmse": rmse, "r2": r2, "spearman": rho,
            "n": int(ok.sum())}


def main() -> None:
    df = pd.read_parquet(DATA)
    is_train = df["train"].to_numpy()
    ycols = ["cut_dia"] + [d for d in POST_DIMS if d != "cut_dia"]

    feat = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    cat_enc = enc.fit_transform(cat)
    X = np.hstack([feat, cat_enc])

    summary = {"task": "phase 5 layer 3 turning/profile-policy benchmark",
               "contract": "wheel_profile_lifecycle_contract_v1",
               "source": str(DATA.relative_to(ROOT)),
               "models": ["B0_global", "B1_shed", "B2_ridge", "C1_xgb"],
               "per_shed_policy": {}, "results": {}}

    # recovered per-shed "B - A" policy, train-only (PIT)
    tr_df = df.loc[is_train]
    shed_med = tr_df.groupby("shed_any")["cut_dia"].median()
    shed_cnt = tr_df.groupby("shed_any")["cut_dia"].count()
    keep = shed_cnt >= MIN_SHED_EVENTS
    for s, med in shed_med[keep].sort_values().items():
        summary["per_shed_policy"][str(s)] = {
            "median_cut": round(float(med), 2),
            "n_events": int(shed_cnt[s]),
        }
    shed_lookup = shed_med[keep]
    g0 = float(tr_df["cut_dia"].median())

    def shed_map(x):
        out = np.full(len(x), g0)
        for i, s in enumerate(shed_lookup.index):
            m = (x == str(s))
            out[m] = shed_lookup.iloc[i]
        return out

    te_df = df.loc[~is_train]
    te_shed = te_df["shed_any"].astype(str).replace({"nan": "NA", "None": "NA"})

    for col, label in POST_DIMS.items():
        y = df[col].to_numpy(dtype=float)
        yok = np.isfinite(y)
        ytr, yte = y[is_train & yok], y[~is_train & yok]
        Xtr_full, Xte_full = X[is_train & yok], X[~is_train & yok]
        if len(yte) < 10:
            continue
        res = {"model_metrics": {}}
        # B0: global train median of post-turn state (or of cut)
        g = float(np.nanmedian(ytr))
        res["model_metrics"]["B0_global"] = metrics(yte, np.full(len(yte), g))
        # B1: per-shed median of post-turn state (PIT shed lookup)
        tr_sub = tr_df.loc[np.isfinite(y[is_train])]
        ps_med = tr_sub.groupby("shed_any")[col].median()
        ps_cnt = tr_sub.groupby("shed_any")[col].count()
        ps_keep = ps_cnt >= MIN_SHED_EVENTS
        ps_lookup = ps_med[ps_keep]
        locks = set(ps_lookup.index)
        yh1 = np.array([ps_lookup[s] if s in locks else g
                        for s in te_shed.to_numpy()])
        res["model_metrics"]["B1_shed"] = metrics(yte, yh1)
        # B2: ridge
        imp = SimpleImputer().fit(Xtr_full)
        r = Ridge(alpha=5.0, random_state=SEED).fit(imp.transform(Xtr_full), ytr)
        res["model_metrics"]["B2_ridge"] = metrics(
            yte, r.predict(imp.transform(Xte_full)))
        # C1: XGB
        xm = XGBRegressor(n_estimators=350, learning_rate=0.07, max_depth=5,
                          subsample=0.85, colsample_bytree=0.85,
                          tree_method="hist", random_state=SEED, verbosity=0)
        xm = xm.fit(Xtr_full, ytr)
        yh_c1 = xm.predict(Xte_full)
        res["model_metrics"]["C1_xgb"] = metrics(yte, yh_c1)
        summary["results"][col] = {"label": label,
                                   "n_train": int(ytr.shape[0]),
                                   "n_test": int(yte.shape[0]),
                                   "model_metrics": res["model_metrics"]}
        print(f"{col}  train={int(ytr.shape[0]):,} test={int(yte.shape[0]):,}"
              f"  C1 mae={res['model_metrics']['C1_xgb']['mae']:.3f}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "turn_policy_benchmark.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    # plots
    rows = summary["results"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    names = summary["models"]
    x = np.arange(len(names))
    for ax, col in zip(axes, ["cut_dia", "post_wsmRoot"]):
        m = rows[col]["model_metrics"]
        maes = [m[n]["mae"] for n in names]
        r2s = [m[n]["r2"] for n in names]
        ax.bar(x, maes, 0.5, color="#5499c7")
        ax.set_xticks(x); ax.set_xticklabels([n.split("_")[0] for n in names])
        ax.set_ylabel("MAE (mm)")
        ax.set_title(f"{col}  (test n={rows[col]['n_test']:,})")
        ax2 = ax.twinx()
        ax2.plot(x, r2s, "o", color="#e74c3c")
        ax2.set_ylabel("R2", color="#e74c3c")
        ax.grid(alpha=0.3)
    fig.suptitle("Layer 3 turn-policy: MAE/R2 by model (temporal PIT split)")
    fig.tight_layout(); fig.savefig(OUT / "turn_policy_mae_r2.png", dpi=130)
    plt.close(fig)

    # scatter: C1 predicted cut vs actual
    y = df["cut_dia"].to_numpy(dtype=float)
    yok = np.isfinite(y)
    Xtr_full, Xte_full = X[is_train & yok], X[~is_train & yok]
    ytr, yte = y[is_train & yok], y[~is_train & yok]
    xm = XGBRegressor(n_estimators=350, learning_rate=0.07, max_depth=5,
                      subsample=0.85, colsample_bytree=0.85,
                      tree_method="hist", random_state=SEED, verbosity=0)
    xm = xm.fit(Xtr_full, ytr)
    yh = xm.predict(Xte_full)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(yte, yh, s=12, alpha=0.35)
    lim = [0, max(float(np.max(yte)), float(np.max(yh))) + 1]
    ax.plot(lim, lim, "r--", lw=1.2)
    ax.set_xlabel("actual cut (mm)"); ax.set_ylabel("predicted cut (mm)")
    ax.set_title(f"C1 cut-dia (test n={int(len(yte)):,})")
    fig.tight_layout(); fig.savefig(OUT / "turn_policy_c1_scatter.png", dpi=130)
    plt.close(fig)

    # per-shed policy bar
    ps = pd.Series(summary["per_shed_policy"]).map(lambda d: d["median_cut"])
    if len(ps):
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ps.sort_values().plot.bar(ax=ax, color="#5499c7")
        ax.set_ylabel("train median cut (mm)")
        ax.set_title("Recovered per-shed 'B - A' policy (train-only)")
        ax.tick_params(axis="x", rotation=60)
        fig.tight_layout(); fig.savefig(OUT / "turn_policy_shed_policy.png",
                                        dpi=130)
        plt.close(fig)

    print(OUT.relative_to(ROOT))
    print(json.dumps(summary, indent=2, default=str)[:2000])


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    main()