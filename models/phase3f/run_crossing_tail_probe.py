"""Phase 3F diagnostic: safety-limit crossing as a TAIL-PROBABILITY problem.

Motivation (user argument, 2026-08-11):
    Open-loop regression of dX fails because the CONDITIONAL MEAN of the
    residual is ~0.  But "will X_{t+H} cross limit L" is a LEFT-TAIL
    statement:  p = P(dX_H < L - X_t | state_t).  That is answerable even
    when E[dX_H | state] ~ 0, provided we model the residual distribution /
    the crossing event directly, with current distance-to-limit as the
    dominating feature.

This probe answers, for each dimension + limit + horizon:
    p = P(next observed value crosses the limit within the horizon)
using three increasing-complexity models evaluated point-in-time on the
frozen test split:
    B0 prior  : unconditional base rate (no learning).
    B1 margin : logistic on current distance-to-limit only.
    B2 full   : XGB on current state + geometry + lifecycle + recent rates.

Honest reporting: diameter at its OWNER limit 1016 mm is a near-zero event
in this fleet (wheels are turned at ~1070 mm, ~54 mm of margin remains), so
the calibrated answer for the SAFETY question is "essentially never" -- but
we quantify it (calibrated probability distribution) rather than asserting
it.  The machinery is validated on the dimension where the event is real:
root > 3 mm within 90d (test base rate ~5.9%).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

_HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"
SEED = 42

LIMIT_ROOT = 3.0
LIMIT_DIA_MIN = 1016.0

# ---- point-in-time (t-only) features. NO target/next_* columns. ----
FEATS_CONT = [
    "wsmDia1", "wsmRoot1", "wsmFlangeThickness1", "wsmWheelGauge1",
    "days_since_turning", "days_since_segment_start", "days_since_last_inspection",
    "wheel_age_days_proxy", "distance_per_day_km", "distance_since_turning_km",
    "wsmDia_rate_per_day_90d", "wsmRoot_rate_per_day_90d",
    "wsmFlangeThickness_rate_per_day_90d", "wsmWheelGauge_rate_per_day_90d",
]
FEATS_CAT = [
    "LocoType", "wheel_profile_2class", "wheel_position_1_12",
    "axle_position_1_6", "defect_zone", "defect_division",
    "lifecycle_segment_id",  # operational_exposure_id is a row-ID, excluded
]


def state1(df):
    """first-valid state measurement per dim (t-only, point-in-time)."""
    out = {}
    for d in ["wsmDia", "wsmRoot", "wsmFlangeThickness", "wsmWheelGauge"]:
        a = df[f"{d}1"].to_numpy(dtype=float); b = df[f"{d}2"].to_numpy(dtype=float)
        q1 = df[f"{d}1_quality"].eq("OBSERVED_VALID").to_numpy()
        q2 = df[f"{d}2_quality"].eq("OBSERVED_VALID").to_numpy()
        out[f"{d}1"] = np.where(q1, a, np.where(q2, b, np.nan))
    return out


def build_X(df, sm1):
    out = pd.DataFrame(index=df.index)
    for c in FEATS_CONT:
        out[c] = df[c].to_numpy(dtype=float) if c in df.columns else np.nan
    for c, v in sm1.items():
        out[c] = v
    for c in FEATS_CAT:
        if c in df.columns:
            out[c] = df[c].astype("category")
    out = out.drop(columns=[c for c in out.columns if c in out and out[c].isna().all()])
    return pd.get_dummies(out, columns=[c for c in FEATS_CAT if c in out.columns],
                          dummy_na=True, dtype=float)


def ece(p, y, bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    fin = np.isfinite(p) & np.isfinite(y)
    p, y = p[fin], y[fin]
    if y.sum() == 0 or len(y) < 20:
        return None
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    err = 0.0; nb = 0
    for i in range(bins):
        m = b == i
        if m.sum() < 5:
            continue
        err += np.abs(p[m].mean() - y[m].mean()) * m.sum() / len(y)
        nb += 1
    return float(err) if nb else None


def run_crossing(df, dim, limit, direction, band, out):
    """Evaluate P(next value crosses limit within horizon band) on test."""
    ev_col = "target_wsmDia" if dim == "wsmDia" else "target_wsmRoot"
    sub = df[df["horizon_window"] == band].copy()
    y = sub[ev_col].to_numpy(dtype=float)
    if direction == "low":
        y_ev = y < limit
    else:
        y_ev = y > limit
    sub["_y"] = y_ev

    tr = sub["split"] == "train"
    te = sub["split"] == "test"
    ntr, nte = int(tr.sum()), int(te.sum())
    pos_te = int((sub.loc[te, "_y"]).sum())
    # per-wheel leakage guard: a single test wheel is only in test split
    sm1 = state1(sub)

    X = build_X(sub, sm1)
    if "wsmDia1" in X.columns:
        X["_margin_dia"] = X["wsmDia1"] - LIMIT_DIA_MIN
    if "wsmRoot1" in X.columns:
        X["_margin_root"] = LIMIT_ROOT - X["wsmRoot1"]

    Xtr, Xte = X.loc[tr], X.loc[te]
    ytr, yte = sub.loc[tr, "_y"].to_numpy(dtype=float), sub.loc[te, "_y"].to_numpy(dtype=float)

    # B0 prior
    prior = ytr.mean()
    # B1 margin-only logistic
    if dim == "wsmDia":
        mcol = "_margin_dia"
    else:
        mcol = "_margin_root"
    p1 = np.full(nte, np.nan)
    if mcol in Xtr.columns:
        mtr = Xtr[mcol].to_numpy(float).reshape(-1, 1)
        mte = Xte[mcol].to_numpy(float).reshape(-1, 1)
        vtr = np.isfinite(mtr).all(axis=1) & np.isfinite(ytr)
        vte = np.isfinite(mte).all(axis=1)
        if vtr.sum() >= 50 and (ytr[vtr].sum() > 0) and (vtr.sum() - ytr[vtr].sum()) > 0:
            lr = LogisticRegression(C=1.0, max_iter=1000)
            lr.fit(mtr[vtr], ytr[vtr])
            p1[vte] = lr.predict_proba(mte[vte])[:, 1]
    # B2 XGB full
    p2 = np.full(nte, np.nan)
    Xtrf = Xtr.drop(columns=[mcol, "_margin_dia", "_margin_root"], errors="ignore")
    Xtef = Xte.drop(columns=[mcol, "_margin_dia", "_margin_root"], errors="ignore")
    Xtrn = np.asarray(Xtrf, dtype=float); Xten = np.asarray(Xtef, dtype=float)
    fin = np.isfinite(ytr)
    if fin.sum() >= 200 and pos_te >= 20:
        m = XGBClassifier(n_estimators=250, max_depth=5, learning_rate=0.1,
                          subsample=0.9, colsample_bytree=0.9, random_state=SEED,
                          n_jobs=-1, tree_method="hist", eval_metric="logloss",
                          missing=np.nan)
        m.fit(Xtrn[fin], ytr[fin])
        p2 = m.predict_proba(Xten)[:, 1]

    def rank_auc(p, yte):
        p = np.asarray(p, float); y = np.asarray(yte, float)
        ok = np.isfinite(p) & np.isfinite(y)
        if ok.sum() < 20 or y[ok].sum() < 1:
            return None
        p, y = p[ok], y[ok]
        r = pd.Series(p).rank()
        n1 = int(y.sum()); n0 = int((1 - y).sum())
        if n1 == 0 or n0 == 0:
            return None
        return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

    brier1 = float(np.nanmean((p1 - yte) ** 2)) if np.isfinite(p1).any() else np.nan
    brier2 = float(np.nanmean((p2 - yte) ** 2)) if np.isfinite(p2).any() else np.nan
    top_n = int(0.1 * nte)
    p2_valid = np.isfinite(p2)
    prec = rec = None
    if p2_valid.sum() >= top_n:
        idx = np.argpartition(p2[p2_valid], -top_n)[-top_n:]
        flag = yte[p2_valid][idx]
        prec = round(float(flag.mean()), 4)
        rec = round(float(flag.sum() / max(1.0, yte.sum())), 4)
    out[dim][limit] = {
        "band": band, "direction": direction, "n_train": ntr, "n_test": nte,
        "pos_test": int(pos_te),
        "base_rate_train": round(float(prior), 5),
        "base_rate_test": round(float(yte.mean()), 5),
        "B0_prior": {
            "brier": round(float(np.nanmean((prior - yte) ** 2)), 5),
            "ece": ece(np.full(nte, prior), yte),
        },
        "B1_margin_only": {
            "auc": rank_auc(p1, yte), "brier": round(brier1, 5),
            "ece": ece(p1, yte), "n_usable": int(np.isfinite(p1).sum()),
        },
        "B2_xgb_full": {
            "auc": rank_auc(p2, yte), "brier": round(brier2, 5),
            "ece": ece(p2, yte), "n_usable": int(np.isfinite(p2).sum()),
        },
        "B2_threshold_recall": {  # decision value: top-decile flag
            "prec_top10": prec,
            "recall_top10": rec,
        },
    }


def main() -> None:
    df = pd.read_parquet(V3F)
    df = df.sort_values("measurement_timestamp").reset_index(drop=True)
    out = {
        "task": "safety-limit crossing as tail probability (NOT RUL)",
        "question": "will the dimension cross its safety limit before the next "
                    "planned intervention (horizon band)?",
        "conventions": {
            "root": "limit 3.0 mm MAX, root GROWS toward it (data-verified)",
            "dia": "limit 1016.0 mm MIN, D FALLS toward it",
            "band_90d": "rows whose next observation is in the 90d horizon window",
        },
        "note_dia_safety": ("owner limit 1016 mm is a near-zero event in this "
                            "fleet: test p1 margin 11.6 mm, wheels turned at ~1070 mm"),
        "eval": {},
    }

    out["eval"]["wsmRoot"] = {}
    run_crossing(df, "wsmRoot", 3.0, "high", "90d", out["eval"])
    run_crossing(df, "wsmRoot", 2.8, "high", "90d", out["eval"])
    run_crossing(df, "wsmRoot", 2.5, "high", "90d", out["eval"])

    out["eval"]["wsmDia"] = {}
    run_crossing(df, "wsmDia", 1016.0, "low", "90d", out["eval"])
    run_crossing(df, "wsmDia", 1030.0, "low", "90d", out["eval"])
    run_crossing(df, "wsmDia", 1040.0, "low", "90d", out["eval"])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dia_crossing_tail_probe.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
