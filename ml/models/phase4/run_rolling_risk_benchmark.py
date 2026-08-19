"""Phase 4 - rolling point-in-time risk benchmark (PRIMARY).

Simulates monthly production deployment: at each cutoff T we may only use
what was knowable at T, then rank the inspections of the trailing window and
evaluate their realized future outcomes.

Point-in-time rules (Risk Event Contract v1.0 section 6):
  - per-equipment observation end is capped at T (we only know observation up
    to T);
  - an event only counts toward the label if it has already occurred by T;
  - features are the frozen v4 point-in-time columns (no future facts).

Per (target, horizon) at each cutoff T:
  train rows = anchor rows with t < T and label determinable at T
  score rows = anchor rows with t in (T-step, T] and label determinable at T
  label: 1 if event strictly inside (t, t+H] (and <= T), 0 otherwise

Models (plan section 7):
  B0 prevalence / random ranking
  B1 regularized logistic (state/context set)
  B2 margin-only logistic (current root margin = 6 - root)
  C1 XGBoost candidate (comparator)

Metrics: PR-AUC (primary), ROC-AUC, Brier, ECE, capture@5%, capture@10%,
lift@5%, lift@10%. Reported as median/IQR across cutoffs - never best-cutoff.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

_HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "model_datasets" / "v4" / "risk_benchmark.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v4"
SEED = 42
# Root wear condemning limit (mm). Source: Wrpld table via
# configs/limit_register_v1.json (root wear 0-6 mm). Supersedes the earlier
# 3 mm figure (degradation_semantics.md Q8, 2026-08-08).
LIMIT_ROOT = 6.0
HORIZONS = (30, 90, 180)
STEP = 30  # monthly refit

# B1 / C1 feature set (numeric, point-in-time)
NUM_FEATS = [
    "wsmDia1", "wsmDia2", "wsmRoot1", "wsmRoot2",
    "wsmFlangeThickness1", "wsmFlangeThickness2", "wsmWheelGauge1", "wsmWheelGauge2",
    "wsmDia_mean", "wsmRoot_mean", "wsmFlangeThickness_mean", "wsmWheelGauge_mean",
    "days_since_turning", "wheel_age_days_proxy", "days_since_last_inspection",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d", "inspection_count_180d",
    "km_last_30d", "km_last_90d", "km_last_180d",
    "wsmRoot_change_last_30d", "wsmRoot_rate_per_day_30d",
    "wsmRoot_change_last_90d", "wsmRoot_rate_per_day_90d",
    "wsmRoot_change_last_180d", "wsmRoot_rate_per_day_180d",
    "wsmDia_change_last_30d", "wsmDia_rate_per_day_30d",
    "wsmDia_change_last_90d", "wsmDia_rate_per_day_90d",
    "wsmFlangeThickness_change_last_30d", "wsmFlangeThickness_rate_per_day_30d",
    "wsmFlangeThickness_change_last_90d", "wsmFlangeThickness_rate_per_day_90d",
    "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_report_count",
    "rtis_reporting_coverage_pct",
]
CAT_FEATS = ["wheel_position_1_12", "axle_position_1_6", "defect_zone",
             "lifecycle_segment_id", "wheel_profile_2class", "home_shed"]


def ece(p, y, bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    if y.sum() == 0 or y.sum() == len(y) or len(y) < 20:
        return None
    edges = np.linspace(0, 1, bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    err = 0.0
    for i in range(bins):
        m = b == i
        if m.sum() < 5:
            continue
        err += np.abs(p[m].mean() - y[m].mean()) * m.sum() / len(y)
    return float(err)


def pr_auc(p, y):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n1 = int(y.sum())
    if n1 == 0 or n1 == len(y):
        return None
    order = np.argsort(-p, kind="mergesort")
    p, y = p[order], y[order]
    # PR-AUC via step function (precision at each recall threshold)
    tp = np.cumsum(y); fp = np.cumsum(1 - y)
    prec = tp / np.maximum(tp + fp, 1)
    # integrate over recall bins
    rec_bins = np.linspace(0, 1, 101)
    vals = []
    for r in rec_bins:
        need = r * n1
        if need == 0:
            vals.append(prec[0] if tp[-1] > 0 else 0.0)
            continue
        idx = np.searchsorted(tp, need, side="left")
        idx = min(max(idx, 0), len(tp) - 1)
        vals.append(prec[idx])
    return float(np.trapz(vals, rec_bins))


def roc_auc(p, y):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n1 = int(y.sum())
    if n1 == 0 or n1 == len(y):
        return None
    r = pd.Series(p).rank()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def capture_at(p, y, k_frac):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n = len(y)
    if n == 0:
        return None
    k = max(1, int(np.floor(k_frac * n)))
    k = min(k, n)
    top = np.argsort(-p, kind="mergesort")[:k]
    return float(y[top].sum() / max(y.sum(), 1.0))


def lift_at(p, y, k_frac):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n = len(y)
    prev = y.mean()
    if prev <= 0:
        return None
    k = max(1, int(np.floor(k_frac * n))); k = min(k, n)
    top = np.argsort(-p, kind="mergesort")[:k]
    return float(y[top].mean() / prev)


def build_matrix(df, fit_mask=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str)
    Xc = pd.get_dummies(cat, dummy_na=True)
    X = np.hstack([Xn, Xc.to_numpy(dtype=float)])
    return X


def main() -> None:
    df = pd.read_parquet(V4)
    wes = pd.read_parquet(WES, columns=[
        "wheelset_equipment_id", "measurement_timestamp",
        "turning_record_at_measurement",
        "wsmRoot1", "wsmRoot2", "wsmRoot1_quality", "wsmRoot2_quality"])

    # ---- point-in-time event structures (per equipment) ----
    r1 = wes["wsmRoot1"].to_numpy(dtype=float); r2 = wes["wsmRoot2"].to_numpy(dtype=float)
    q1 = wes["wsmRoot1_quality"].eq("OBSERVED_VALID").to_numpy()
    q2 = wes["wsmRoot2_quality"].eq("OBSERVED_VALID").to_numpy()
    wes["_root"] = np.where(q1 & q2, (r1 + r2) / 2.0, np.where(q1, r1, np.where(q2, r2, np.nan)))
    wes["_turn"] = wes["turning_record_at_measurement"].eq(1).to_numpy()
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    wes["_t"] = pd.to_datetime(wes["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    wes["_eq"] = wes["wheelset_equipment_id"].astype("int64").to_numpy()

    # first-event-after-t per anchor row (static), per equipment
    eq_groups = wes.groupby("_eq", sort=False).groups
    eq_times = {}
    eq_root = {}
    eq_turn = {}
    for eq, idx in eq_groups.items():
        idx = idx.to_numpy()
        ts = wes["_t"].to_numpy()[idx]
        rt = wes["_root"].to_numpy()[idx]
        tn = wes["_turn"].to_numpy()[idx]
        order = np.argsort(ts, kind="mergesort")
        eq_times[int(eq)] = ts[order]
        eq_root[int(eq)] = rt[order]
        eq_turn[int(eq)] = tn[order]

    t0 = pd.to_datetime(df["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    eq = df["wheelset_equipment_id"].astype("int64").to_numpy()

    # static: first root>6 event strictly after t; first turn event after t
    first_root = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    first_turn = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    obs_end_full = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    for i in range(len(df)):
        e = int(eq[i]); t = t0[i]
        ts = eq_times.get(e)
        if ts is None or ts.size == 0:
            continue
        j = np.searchsorted(ts, t, side="right")
        if j >= ts.size:
            obs_end_full[i] = ts[-1]
            continue
        obs_end_full[i] = ts[-1]
        rt = eq_root[e][j:]; tn = eq_turn[e][j:]
        tsj = ts[j:]
        rk = np.flatnonzero(rt > LIMIT_ROOT)
        if rk.size:
            first_root[i] = tsj[rk[0]]
        tk = np.flatnonzero(tn)
        if tk.size:
            first_turn[i] = tsj[tk[0]]

    # obs end as-of T (last measurement of equipment <= T) -- cached per cutoff
    obs_cache = {}

    def obs_asof(T):
        key = int(T.astype("int64"))
        if key in obs_cache:
            return obs_cache[key]
        out = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
        for e in list(eq_times.keys()):
            ts = eq_times[e]
            if ts.size == 0:
                continue
            m = eq == e
            if not m.any():
                continue
            j = np.searchsorted(ts, T, side="right") - 1
            if j >= 0:
                out[m] = ts[j]
        obs_cache[key] = out
        return out

    # ---- cutoffs: monthly grid spanning the anchor time range ----
    tmin = pd.to_datetime(df["measurement_timestamp"]).min()
    tmax = pd.to_datetime(df["measurement_timestamp"]).max()
    cutoffs = pd.date_range(start=tmin + pd.Timedelta(days=180), end=tmax, freq=f"{STEP}D")

    all_rows = pd.DataFrame({
        "t": t0, "eq": eq, "first_root": first_root, "first_turn": first_turn,
        "obs_end_full": obs_end_full,
    })

    Xall = build_matrix(df)

    out = {"task": "phase 4 rolling point-in-time risk benchmark",
           "step_days": STEP, "horizons": {}, "targets": {}}

    for target, ev_time, ev_name in (("root", "first_root", "root_within"),
                                     ("turn", "first_turn", "turn_within")):
        for H in HORIZONS:
            ev = all_rows[ev_time].to_numpy()
            in_win = (ev != np.datetime64("NaT")) & ((ev - t0) <= np.timedelta64(H, "D"))
            y_true = in_win.astype(float)
            # static (full-hindsight) eligibility for scoring: label known once
            # the whole window has elapsed or an event occurred
            static_elig = ((all_rows["obs_end_full"].to_numpy() - t0) >= np.timedelta64(H, "D")) | in_win
            col_cutoffs = []
            for T in cutoffs:
                Tn = np.datetime64(T, "us")
                obs = obs_asof(Tn)
                full_by_T = (obs - t0) >= np.timedelta64(H, "D")
                event_by_T = in_win & (ev <= Tn)
                known = full_by_T | event_by_T

                # train: rows before T whose label is determinable at T
                tr_mask = (t0 < Tn) & known
                # score: trailing-window rows (all; label evaluated with hindsight)
                sc_mask = (t0 > Tn - np.timedelta64(STEP, "D")) \
                    & (t0 <= Tn) & static_elig
                ntr = int(tr_mask.sum()); nsc = int(sc_mask.sum())
                ev_tr = int(y_true[tr_mask].sum()); ev_sc = int(y_true[sc_mask].sum())
                if ntr < 500 or nsc < 200 or ev_sc < 10:
                    continue

                ytr = y_true[tr_mask]; ysc = y_true[sc_mask]
                # ---- B0 prevalence ----
                prev = ytr.mean()
                p0 = np.full(nsc, prev)
                # ---- B1 regularized logistic ----
                Xtr = Xall[tr_mask]; Xsc = Xall[sc_mask]
                Xtrf = np.nan_to_num(Xtr, nan=0.0); Xscf = np.nan_to_num(Xsc, nan=0.0)
                sc = StandardScaler().fit(Xtrf)
                Xtrs = sc.transform(Xtrf); Xscs = sc.transform(Xscf)
                lr = LogisticRegression(C=0.1, max_iter=1000, random_state=SEED)
                lr.fit(Xtrs, ytr)
                p1 = lr.predict_proba(Xscs)[:, 1]
                # ---- B2 margin-only logistic ----
                mcol = df["wsmRoot_mean"].to_numpy(dtype=float)
                marg = LIMIT_ROOT - mcol
                mt = marg[tr_mask].reshape(-1, 1); ms = marg[sc_mask].reshape(-1, 1)
                okm = np.isfinite(mt).ravel()
                p2 = np.full(nsc, np.nan)
                if okm.sum() >= 50 and ytr[okm].sum() > 0 and (okm.sum() - ytr[okm].sum()) > 0:
                    lrm = LogisticRegression(C=1.0, max_iter=1000)
                    lrm.fit(mt[okm], ytr[okm])
                    p2 = lrm.predict_proba(np.nan_to_num(ms, nan=0.0))[:, 1]
                # ---- C1 XGBoost ----
                p3 = np.full(nsc, np.nan)
                subsample = min(len(ytr), 40000)
                rng = np.random.default_rng(SEED)
                if len(ytr) > subsample:
                    keep = rng.choice(len(ytr), subsample, replace=False)
                    Xtrs2, ytr2 = Xtrs[keep], ytr[keep]
                else:
                    Xtrs2, ytr2 = Xtrs, ytr
                xgb = XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                                    subsample=0.9, colsample_bytree=0.9,
                                    random_state=SEED, n_jobs=-1, tree_method="hist",
                                    eval_metric="logloss")
                xgb.fit(Xtrs2, ytr2)
                p3 = xgb.predict_proba(Xscs)[:, 1]

                col_cutoffs.append({
                    "cutoff": str(T.date()), "train_n": ntr, "score_n": nsc,
                    "train_events": ev_tr, "score_events": ev_sc,
                    "prevalence": round(float(prev), 5),
                    "B0": {"pr_auc": pr_auc(p0, ysc), "roc_auc": roc_auc(p0, ysc),
                           "brier": round(float(np.mean((p0 - ysc) ** 2)), 5),
                           "capture5": capture_at(p0, ysc, 0.05), "capture10": capture_at(p0, ysc, 0.10)},
                    "B1_logistic": {"pr_auc": pr_auc(p1, ysc), "roc_auc": roc_auc(p1, ysc),
                                    "brier": round(float(np.mean((p1 - ysc) ** 2)), 5),
                                    "ece": ece(p1, ysc),
                                    "capture5": capture_at(p1, ysc, 0.05),
                                    "capture10": capture_at(p1, ysc, 0.10),
                                    "lift5": lift_at(p1, ysc, 0.05),
                                    "lift10": lift_at(p1, ysc, 0.10)},
                    "B2_margin": {"pr_auc": pr_auc(p2, ysc), "roc_auc": roc_auc(p2, ysc),
                                  "brier": round(float(np.nanmean((p2 - ysc) ** 2)), 5),
                                  "ece": ece(p2, ysc),
                                  "capture5": capture_at(p2, ysc, 0.05),
                                  "capture10": capture_at(p2, ysc, 0.10)},
                    "C1_xgb": {"pr_auc": pr_auc(p3, ysc), "roc_auc": roc_auc(p3, ysc),
                               "brier": round(float(np.nanmean((p3 - ysc) ** 2)), 5),
                               "ece": ece(p3, ysc),
                               "capture5": capture_at(p3, ysc, 0.05),
                               "capture10": capture_at(p3, ysc, 0.10),
                               "lift5": lift_at(p3, ysc, 0.05),
                               "lift10": lift_at(p3, ysc, 0.10)},
                })

            # ---- aggregate: median / IQR across cutoffs ----
            def med_iqr(key, model):
                vals = [c[model][key] for c in col_cutoffs
                        if c[model].get(key) is not None]
                if not vals:
                    return None
                return {"median": round(float(np.median(vals)), 4),
                        "p25": round(float(np.percentile(vals, 25)), 4),
                        "p75": round(float(np.percentile(vals, 75)), 4),
                        "n_cutoffs": int(len(vals))}

            out["targets"].setdefault(target, {})[str(H)] = {
                "n_cutoffs": int(len(col_cutoffs)),
                "prevalence_median": round(float(np.median([c["prevalence"] for c in col_cutoffs])), 5) if col_cutoffs else None,
                "B0": {"pr_auc": med_iqr("pr_auc", "B0"), "capture5": med_iqr("capture5", "B0"),
                       "capture10": med_iqr("capture10", "B0")},
                "B1_logistic": {"pr_auc": med_iqr("pr_auc", "B1_logistic"),
                                "roc_auc": med_iqr("roc_auc", "B1_logistic"),
                                "brier": med_iqr("brier", "B1_logistic"), "ece": med_iqr("ece", "B1_logistic"),
                                "capture5": med_iqr("capture5", "B1_logistic"),
                                "capture10": med_iqr("capture10", "B1_logistic"),
                                "lift5": med_iqr("lift5", "B1_logistic"),
                                "lift10": med_iqr("lift10", "B1_logistic")},
                "B2_margin": {"pr_auc": med_iqr("pr_auc", "B2_margin"),
                              "roc_auc": med_iqr("roc_auc", "B2_margin"),
                              "brier": med_iqr("brier", "B2_margin"), "ece": med_iqr("ece", "B2_margin"),
                              "capture5": med_iqr("capture5", "B2_margin"),
                              "capture10": med_iqr("capture10", "B2_margin")},
                "C1_xgb": {"pr_auc": med_iqr("pr_auc", "C1_xgb"),
                           "roc_auc": med_iqr("roc_auc", "C1_xgb"),
                           "brier": med_iqr("brier", "C1_xgb"), "ece": med_iqr("ece", "C1_xgb"),
                           "capture5": med_iqr("capture5", "C1_xgb"),
                           "capture10": med_iqr("capture10", "C1_xgb"),
                           "lift5": med_iqr("lift5", "C1_xgb"),
                           "lift10": med_iqr("lift10", "C1_xgb")},
            }
            print(f"  {target:5s} H={H:3d} cutoffs={len(col_cutoffs)} done")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "rolling_risk_benchmark.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
