"""Phase 5 Layer 5 - turning-probability benchmark (P(turn)).

Predicts whether a wheelset will be turned (maintenance behaviour) within
30/60/90 days from a point-in-time anchor (the v5 turn_probability substrate).
This models HISTORICAL turning behaviour - NOT engineering-limit/end-of-life
risk, and NOT a "must turn" recommendation.

Models per horizon:
  B0_prevalence  constant rate from the train split
  B1_shed        per-shed train turn rate (home_shed level, missing -> overall)
  C1_xgb         XGBClassifier on native NaN features (point-in-time only)

Metrics (classification + calibration + operational ranking):
  ROC-AUC, PR-AUC, Brier, ECE (10-bin calibration), capture@topk
  (share of actual turns captured in the top-k rows by predicted P(turn)),
  cohort/shed breakdown (ROC-AUC + turn rate + n by home_shed on the test set).

Output: models/experiments/v5/turn_probability_benchmark.json + plots + md.
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
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "model_datasets" / "v5" / "turn_probability.parquet"
OUT = ROOT / "models" / "experiments" / "v5"

HORIZONS = (30, 60, 90)
SEED = 42

NUM_FEATS = [
    "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
    "mean_wsmFlangeThickness", "mean_wsmWheelGauge",
    "ph5_wsmFlange_rate_per_day_30d", "ph5_wsmFlange_rate_per_day_90d",
    "ph5_wsmThread_rate_per_day_30d", "ph5_wsmThread_rate_per_day_90d",
    "wsmRoot_rate_per_day_30d", "wsmRoot_rate_per_day_90d",
    "wsmDia_rate_per_day_30d", "wsmDia_rate_per_day_90d",
    "days_since_turning", "distance_since_turning_km",
    "days_since_last_inspection", "wheel_age_days_proxy",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d",
    "km_last_30d", "km_last_90d",
    "rtis_reporting_coverage_pct", "distance_per_day_km",
    "n_prior_turns", "segment_index",
    "axle_position_1_6", "wheel_position_1_12", "wheel_profile_2class",
]
CAT_FEATS = ["LocoType", "home_shed", "defect_zone", "shed_any"]


def build_matrix(df, enc=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA", "<NA>": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(cat)
    else:
        Xc = enc.transform(cat)
    return Xn, Xc, enc


def decile_calibration(y_tr, p_tr):
    """Empirical reliability band (Phase 4 method): training-split score deciles
    mapped to the realized event rate in each decile.

    Returns bin_edges, bin_rates. At serve time a raw score is binned against
    bin_edges and its decile's realized rate is the calibrated band. Only valid
    for the model whose training scores produced it (the serving C1 uses the
    same config and train split, so it carries over).
    """
    ok = np.isfinite(p_tr) & np.isfinite(y_tr)
    y, p = y_tr[ok], p_tr[ok]
    if p.size < 100:
        return None, None
    edges = np.percentile(p, np.arange(0, 101, 10))          # 11 edges, 10 bins
    dec = np.clip(np.digitize(p, edges[1:-1]), 0, 9)
    rates = [float(y[dec == i].mean()) if (dec == i).sum() else None
             for i in range(10)]
    return [round(float(e), 6) for e in edges], rates


def ece(y, p, bins=10):
    ok = np.isfinite(p) & np.isfinite(y)
    y, p = y[ok], p[ok]
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if not np.any(m):
            continue
        tot += (len(p[m]) / len(p)) * abs(float(np.mean(p[m]) - np.mean(y[m])))
    return round(float(tot), 4)


def capture_topk(y, p, k_fracs=(0.01, 0.05, 0.10)):
    ok = np.isfinite(p) & np.isfinite(y)
    y, p = y[ok], p[ok]
    n = len(y)
    n_turn = int(y.sum())
    res = {}
    for kf in k_fracs:
        k = max(1, int(np.floor(kf * n)))
        top = np.argsort(-p, kind="mergesort")[:k]
        cap = int(y[top].sum())
        res[f"top{int(kf*100):d}%"] = {
            "k": k, "turns_captured": cap,
            "share_of_turns": round(cap / n_turn, 4) if n_turn else None,
            "precision": round(cap / k, 4),
        }
    return res


def fit_xgb(tr_idx, te_idx, ytr, yte, enc):
    Xn_tr, Xc_tr, _ = build_matrix(tr_idx)
    Xn_te, Xc_te, _ = build_matrix(te_idx, enc)
    m = XGBClassifier(n_estimators=400, learning_rate=0.08, max_depth=6,
                      subsample=0.85, colsample_bytree=0.85,
                      tree_method="hist", random_state=SEED, verbosity=0,
                      eval_metric="logloss")
    m.fit(np.hstack([Xn_tr, Xc_tr]), ytr)
    p = m.predict_proba(np.hstack([Xn_te, Xc_te]))[:, 1]
    return p


def main() -> None:
    df = pd.read_parquet(DATA)
    is_train = df["split"].eq("train").to_numpy()
    tr_raw = df[is_train].reset_index(drop=True)
    te_raw = df[~is_train].reset_index(drop=True)

    summary = {"task": "phase 5 layer 5 turning-probability benchmark (maintenance behaviour)",
               "contract": "wheel_profile_lifecycle_contract_v1",
               "pointer": "P(turn) = historical maintenance behaviour, NOT engineering-limit risk",
               "source": str(DATA.relative_to(ROOT)),
               "models": ["B0_prevalence", "B1_shed", "C1_xgb"],
               "horizons": {str(H): {} for H in HORIZONS}}

    # B1: per-shed train rates - shed_any primary (rich), home_shed fallback
    rate_any = tr_raw.groupby("shed_any")["turned_30d"].mean()
    rate_own = tr_raw.groupby("home_shed")["turned_30d"].mean()

    fig, axes = plt.subplots(1, len(HORIZONS), figsize=(18, 5))
    for ax, H in zip(axes, HORIZONS):
        tgt = f"turned_{H}d"
        ytr = tr_raw[tgt].to_numpy(dtype=float)
        yte = te_raw[tgt].to_numpy(dtype=float)
        tr_ok = np.isfinite(ytr)
        te_ok = np.isfinite(yte)
        tr_idx = tr_raw[tr_ok].reset_index(drop=True)
        te_idx = te_raw[te_ok].reset_index(drop=True)
        ytr, yte = ytr[tr_ok], yte[te_ok]

        prev = float(np.mean(ytr))
        p0 = np.full(len(yte), prev)
        s_any = te_idx["shed_any"].astype(str).values
        s_own = te_idx["home_shed"].astype(str).values
        p1 = np.array([
            rate_any.get(a, rate_own.get(o, prev))
            for a, o in zip(s_any, s_own)], float)

        enc = None
        Xn_tr, Xc_tr, enc = build_matrix(tr_idx)
        m = XGBClassifier(n_estimators=400, learning_rate=0.08, max_depth=6,
                          subsample=0.85, colsample_bytree=0.85,
                          tree_method="hist", random_state=SEED, verbosity=0,
                          eval_metric="logloss")
        m.fit(np.hstack([Xn_tr, Xc_tr]), ytr)
        Xn_te, Xc_te, _ = build_matrix(te_idx, enc)
        p2 = m.predict_proba(np.hstack([Xn_te, Xc_te]))[:, 1]
        # Phase 4 reliability band: C1 training-split score deciles -> realized
        # train event rate. Model-consistent with the serving C1 (same config +
        # train split), so it is what the dashboard applies to served scores.
        p2_tr = m.predict_proba(np.hstack([Xn_tr, Xc_tr]))[:, 1]
        cal_edges, cal_rates = decile_calibration(ytr, p2_tr)
        calibration = ({"method": "empirical score deciles (Phase 4)",
                        "n_type": "train",
                        "cutoff_based": True,
                        "bin_edges": cal_edges, "bin_rates": cal_rates,
                        "train_prevalence": round(float(np.mean(ytr)), 6)}
                       if cal_edges is not None else None)

        per_model = {}
        for name, p in (("B0_prevalence", p0), ("B1_shed", p1), ("C1_xgb", p2)):
            ok = np.isfinite(p)
            mdict = {
                "n_test": int(len(yte)),
                "turn_rate_test": round(float(np.mean(yte)), 4),
                "turn_rate_pred": round(float(np.mean(p)), 4),
            }
            try:
                mdict["roc_auc"] = round(float(roc_auc_score(yte[ok], p[ok])), 4)
            except ValueError:
                mdict["roc_auc"] = None
            try:
                mdict["pr_auc"] = round(float(average_precision_score(yte[ok], p[ok])), 4)
            except ValueError:
                mdict["pr_auc"] = None
            mdict["brier"] = round(float(brier_score_loss(yte[ok], p[ok])), 4)
            mdict["ece"] = ece(yte, p)
            mdict["capture"] = capture_topk(yte, p)
            if name == "C1_xgb" and calibration is not None:
                mdict["calibration"] = calibration
            per_model[name] = mdict
        summary["horizons"][str(H)] = {"models": per_model}
        print(f"P(turn) {H}d  train={int(ytr.sum()):,}/{len(ytr):,} "
              f"test={int(yte.sum()):,}/{len(yte):,}")

        # calibration + ROC curve for C1
        from sklearn.metrics import roc_curve
        fpr, tpr, _ = roc_curve(yte, p2)
        ax.plot(fpr, tpr, lw=1.6, label=f"C1 (AUC {per_model['C1_xgb']['roc_auc']})")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8)
        ax.set_title(f"P(turn) {H}d (test rate {np.mean(yte):.3f})")
        ax.set_xlabel("FPR"); ax.set_ylabel("TPR"); ax.legend(); ax.grid(alpha=0.3)

    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "turn_probability_roc.png", dpi=130)
    plt.close(fig)

    # cohort / shed breakdown on C1 (90d) test set
    H = 90
    tgt = f"turned_{H}d"
    yte_all = te_raw[tgt].to_numpy(dtype=float)
    te_ok = np.isfinite(yte_all)
    te_idx = te_raw[te_ok].reset_index(drop=True)
    yte = yte_all[te_ok]
    prev = float(np.mean(tr_raw[tgt].to_numpy(dtype=float)))
    enc = None
    Xn_tr, Xc_tr, enc = build_matrix(tr_raw[tr_raw[tgt].notna()].reset_index(drop=True))
    m = XGBClassifier(n_estimators=400, learning_rate=0.08, max_depth=6,
                      subsample=0.85, colsample_bytree=0.85,
                      tree_method="hist", random_state=SEED, verbosity=0,
                      eval_metric="logloss")
    ytr = tr_raw[tgt].to_numpy(dtype=float)
    m.fit(np.hstack([Xn_tr, Xc_tr]), ytr[~np.isnan(ytr)])
    Xn_te, Xc_te, _ = build_matrix(te_idx, enc)
    p2 = m.predict_proba(np.hstack([Xn_te, Xc_te]))[:, 1]
    te_idx = te_idx.assign(_y=yte, _p=p2)

    sheds = []
    for s, g in te_idx.groupby("shed_any"):
        if len(g) < 30 or g["_y"].sum() == 0 or len(g["_y"].unique()) < 2:
            continue
        try:
            auc = round(float(roc_auc_score(g["_y"], g["_p"])), 3)
        except ValueError:
            auc = None
        sheds.append({"shed": str(s), "n": int(len(g)),
                      "turn_rate": round(float(g["_y"].mean()), 3),
                      "roc_auc": auc})
    sheds.sort(key=lambda d: -d["n"])
    summary["shed_breakdown_90d"] = sheds[:25]
    print("top sheds (90d):", [(d["shed"], d["n"], d["turn_rate"], d["roc_auc"]) for d in sheds[:8]])

    (OUT / "turn_probability_benchmark.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    main()
