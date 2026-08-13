"""Phase 3C - distance vs calendar-time information content + degradation rate
under exposure (companion to run_diagnostic_forensics.py).

Question 1: Does approved RTIS distance explain future within-life wheel state
            degradation that CALENDAR TIME cannot?
Question 2: How fast is the wheel actually degrading under a given exposure?

Design for Q1 (alignment-safe, same cohorts both arms):
  - Subset BOTH train and test to rows where interval_distance_km is OBSERVED
    (distance_available=True) so leftover-rows are identical between arms.
  - Arm T  (time, no distance): state + quality + calendar/time + categoricals
  - Arm TD (time + distance): Arm T + interval_distance_km + distance_per_day_km
    + coverage + distance_since_turning_km
  - Same frozen test ids, same rows, same XGBoost hypers/seed, same target.
  - Report MAE/RMSE/R2 + band stratifications on the distance-ok test subset.

Design for Q2 (descriptive, within-life pairs only):
  - per-pair observed change delta_d = target - base (signed; +ve = state grew)
  - mm/day  = delta_d / interval_days (calendar speed)
  - mm/1kkm = delta_d / (interval_distance_km/1e3) (usage-specific speed)
  - reported as median/IQR per dimension, and per distance/day bands.

No tuning, no feature expansion: XGBoost config fixed exactly as the clean
benchmark. Alignment asserted per fit.
"""
from __future__ import annotations

import json
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))

from degradation_eval import (  # noqa: E402
    ROW_ID_COL, DIMENSIONS, add_targets_and_bases,
    chronological_split, _reg_metrics,
)
from run_clean_degradation_benchmark import _base_num_cols, _prepare  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / "model_datasets" / "v3c" / "clean_benchmark_pairs.parquet"
COHORT = ROOT / "model_datasets" / "v3c" / "clean_benchmark_cohort.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3c"
SEED = 42
DIST_FEATURES = ["interval_distance_km", "distance_per_day_km",
                 "rtis_distance_coverage_pct_in_interval", "distance_since_turning_km"]

EDGES_KM = [0, 1000, 5000, 15000, 30000, 1e9]
EDGES_KMPD = [0, 100, 250, 450, 650, 1e9]


def _band(v, edges):
    i = bisect_left(edges, float(v))
    if i <= 0:
        return f"<{edges[0]}"
    lo = "" if edges[i] == 1e9 else str(edges[i])
    return f"{edges[i-1]}-{lo}" if lo else f">{edges[i-1]}"


def fit_xgb_on(w, trmask, temask, cols, d, seed=SEED):
    from xgboost import XGBRegressor
    Xtr = _prepare(w, cols).loc[trmask].to_numpy()
    Xte = _prepare(w, cols).loc[temask].to_numpy()
    y = w[f"target_{d}"].to_numpy(dtype=float)
    ytr = y[trmask]
    yte = y[temask]
    fin = np.isfinite(ytr)
    m = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                     subsample=1.0, colsample_bytree=1.0, random_state=seed,
                     n_jobs=-1, tree_method="hist")
    m.fit(Xtr[fin], ytr[fin])
    pred = m.predict(Xte)
    return m, _reg_metrics(yte, pred)


def _rob(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"n": 0}
    return {"n": int(x.size), "median": round(float(np.median(x)), 5),
            "q25": round(float(np.quantile(x, .25)), 5),
            "q75": round(float(np.quantile(x, .75)), 5)}


def main() -> None:
    raw = pd.read_parquet(SUBSTRATE)
    df = raw[raw["within_lifecycle"]].copy()
    df = add_targets_and_bases(df)
    w, tr_mask, te_mask = chronological_split(df, test_frac=0.2, cache_path=COHORT)

    d_ok = w["distance_available"].fillna(False).to_numpy()
    tr_ok = d_ok & tr_mask
    te_ok = d_ok & te_mask
    n_te = int(te_ok.sum())

    cols_t = _base_num_cols()
    cols_td = cols_t + DIST_FEATURES

    # persistent baseline restricted to the distance-ok TEST subset
    te_sub = w.loc[te_ok]
    persist_sub = {}
    for d in DIMENSIONS:
        persist_sub[d] = _reg_metrics(
            te_sub[f"target_{d}"].to_numpy(dtype=float),
            te_sub[f"base_{d}"].to_numpy(dtype=float))

    abl = {}
    for d in DIMENSIONS:
        # Arm T vs TD on the SAME distance-ok train/test subset
        _, mT = fit_xgb_on(w, tr_ok, te_ok, cols_t, d)
        _, mTD = fit_xgb_on(w, tr_ok, te_ok, cols_td, d)
        abl[d] = {
            "n_test_subset": n_te,
            "persistence_on_dist_test": persist_sub[d],
            "time_only": mT,
            "time_plus_distance": mTD,
            "delta_mae_time_vs_dist": round(mT["mae"] - mTD["mae"], 4),
            "delta_rmse_time_vs_dist": round(mT["rmse"] - mTD["rmse"], 4),
            "r2_time_only": mT["r2"], "r2_time_plus_dist": mTD["r2"],
            "spearman_time_only": mT["spearman"], "spearman_time_plus_dist": mTD["spearman"],
        }

    # ------------------------------------------------------------------ #
    # Q2: degradation speed under exposure (within-life pairs, all rows)
    # ------------------------------------------------------------------ #
    rates = {}
    for d in DIMENSIONS:
        dd = w[f"target_{d}"].to_numpy(dtype=float) - w[f"base_{d}"].to_numpy(dtype=float)
        days = w["interval_days"].to_numpy(dtype=float)
        dist = w["interval_distance_km"].to_numpy(dtype=float)
        ok = np.isfinite(dd) & np.isfinite(days)
        dr = np.where(ok & (days > 0), dd / days, np.nan)
        km_ok = ok & np.isfinite(dist) & (dist > 0) & d_ok
        kr = np.where(km_ok, dd / (dist / 1e3), np.nan)

        dayrate = dr
        kmrate = kr

        # by distance band
        db = w["interval_distance_km"].apply(lambda v: _band(v, EDGES_KM) if np.isfinite(v) else "NA")
        kmpd = w["distance_per_day_km"].apply(lambda v: _band(v, EDGES_KMPD) if np.isfinite(v) else "NA")
        dbp = w["rtis_distance_coverage_pct_in_interval"].apply(
            lambda v: _band(v, [0, 25, 50, 75, 100, 1e9]) if np.isfinite(v) else "NA")

        rates[d] = {
            "n_pairs": int(ok.sum()),
            "median_interval_days": round(float(np.nanmedian(days[ok])), 1),
            "mm_per_day": _rob(dayrate),
            "mm_per_1000km": _rob(kmrate),
            "dayrate_by_dist_km": {str(k): _rob(dayrate[db.to_numpy() == k])
                                   for k in sorted(set(db))},
            "kmrate_by_dist_km": {str(k): _rob(kmrate[db.to_numpy() == k])
                                  for k in sorted(set(db))},
            "kmrate_by_km_per_day": {str(k): _rob(kmrate[kmpd.to_numpy() == k])
                                     for k in sorted(set(kmpd))},
            "kmrate_by_coverage_pct": {str(k): _rob(kmrate[dbp.to_numpy() == k])
                                       for k in sorted(set(dbp))},
        }

    out = {
        "task": "Phase 3C distance-vs-time ablation & exposure-rate diagnostics",
        "seed": SEED,
        "n_train": int(tr_mask.sum()), "n_test": int(te_mask.sum()),
        "n_distance_ok_train": int(tr_ok.sum()), "n_distance_ok_test": n_te,
        "design": "Both arms trained on the SAME distance-available train rows "
                  "and evaluated on the SAME distance-available test rows.",
        "ablation": abl,
        "exposure_rates": rates,
    }

    OUT = OUTPUT / "diagnostic_distance_time_ablation.json"
    OUT.write_text(json.dumps(out, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    print(OUT)
    print(f"distance-ok train={int(tr_ok.sum())} test={n_te}")
    for d in DIMENSIONS:
        a = abl[d]
        print(f"{d:18s} persist={a['persistence_on_dist_test']['mae']:.4f} "
              f"T={a['time_only']['mae']:.4f} TD={a['time_plus_distance']['mae']:.4f} "
              f"delta={a['delta_mae_time_vs_dist']:+.4f} "
              f"(r2 T={a['r2_time_only']:.3f} TD={a['r2_time_plus_dist']:.3f})")
    print("--- exposure rates ---")
    for d in DIMENSIONS:
        r = rates[d]
        print(f"{d:18s} mm/day med={r['mm_per_day']['median']} "
              f"mm/1kkm med={r['mm_per_1000km'].get('median')} "
              f"(n={r['mm_per_1000km'].get('n')})")


if __name__ == "__main__":
    main()