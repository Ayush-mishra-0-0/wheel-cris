"""Phase 3D - horizon-windowed forecast benchmark (split conformal, two arms).

Framing: horizon-windowed future-state forecasting, NOT exact 30/60/90-day
prediction. For each nominal horizon H we forecast X(t+H) = X(t) + dX(H) and
evaluate only on real within-life pairs whose actual interval_days falls
inside the window (docs/phase3c_plan.md §10). One XGBoost per (arm, dimension)
predicts the next measured absolute state; interval_days is a continuous
feature, so the same model serves every band and is only *evaluated* per band.

Arms (identical rows / order / split / seeds / hyperparameters):
  Arm A  time/state-only  : state cols, quality codes, exposure, categoricals
  Arm B  state(+distance) : Arm A + interval_distance_km, distance_per_day_km,
                            rtis_distance_coverage_pct_in_interval,
                            distance_since_turning_km, distance_available

Uncertainty: split conformal. Calibration = last 10% of the chronological
TRAIN set (before the frozen test cohort), never the test rows. Per (dimension,
band, arm, nominal level) the interval width is a finite-sample order
statistic of |y - yhat| on calibration rows restricted to that band. Coverage
on the test cohort is EMPIRICAL TEMPORAL COVERAGE - an observed diagnostic,
not an unconditional guarantee.

Reporting per (dimension, band, arm) uses three clearly-labelled views:
  1. full_test             the full frozen test cohort
  2. distance_present      distance_available == True
  3. coverage_restricted   measurement_timestamp <= 2025-12-31 (ledger end)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3c"))

from degradation_eval import (  # noqa: E402
    ROW_ID_COL, DIMENSIONS, STATE_COLUMNS, QUALITY_COLUMNS, EXPOSURE_COLUMNS,
    CATEGORICAL_COLUMNS, add_targets_and_bases, add_historical_rate_predictions,
    fit_xgb, _reg_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
V3D = ROOT / "model_datasets" / "v3d" / "forecast_horizon_benchmark_pairs.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3d"
SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")

BANDS = ["30d", "60d", "90d", "180d", "365d"]
NOMINAL = {"i80": 0.20, "i95": 0.05}

DIST_FEATURES = [
    "interval_distance_km", "distance_per_day_km",
    "rtis_distance_coverage_pct_in_interval", "distance_since_turning_km",
    "distance_available",
]


def reg_cols() -> list[str]:
    return (STATE_COLUMNS + EXPOSURE_COLUMNS
            + [c + "_code" for c in QUALITY_COLUMNS] + CATEGORICAL_COLUMNS)


def prepare_matrix(wear: pd.DataFrame, num_cols: list[str]) -> np.ndarray:
    enc = wear.copy()
    for c in QUALITY_COLUMNS:
        enc[c + "_code"] = enc[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    for c in CATEGORICAL_COLUMNS:
        vals = sorted(enc[c].dropna().astype(str).unique())
        code = {v: i for i, v in enumerate(vals)}
        enc[c] = enc[c].astype(str).map(code).astype(float).fillna(-1.0)
    M = enc[num_cols].astype(float).fillna(0.0)
    if "distance_available" in enc.columns:
        M["distance_available"] = enc["distance_available"].fillna(False).astype(float)
    return M.to_numpy().astype(np.float64)


def conformal_width(resid: np.ndarray, alpha: float) -> float | None:
    s = np.asarray(resid, dtype=float)
    s = s[np.isfinite(s)]
    if s.size < 10:
        return None
    k = int(np.ceil((s.size + 1) * (1.0 - alpha)))
    k = min(max(k, 1), s.size)
    return float(np.partition(s, k - 1)[k - 1])


def coverage_view(yt, yp, width) -> dict:
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    valid = np.isfinite(yt) & np.isfinite(yp)
    n = int(valid.sum())
    if n == 0:
        return {"n": 0}
    if width is None:
        return {"n": n, "empirical_coverage": None, "mean_width": None}
    hit = int(np.sum(np.abs(yt[valid] - yp[valid]) <= width))
    return {"n": n, "empirical_coverage": round(hit / n, 4), "mean_width": round(float(width), 4)}


def main() -> None:
    wes = pd.read_parquet(V3D)
    wes = add_targets_and_bases(wes)  # idempotent (same row set)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    tr_mask = (wes["split"] == "train").to_numpy()
    te_mask = (wes["split"] == "test").to_numpy()
    n_train = int(tr_mask.sum())
    n_test = int(te_mask.sum())

    # historical-rate trajectory baseline (point-in-time, per wheelset)
    hr = add_historical_rate_predictions(wes)
    for d in DIMENSIONS:
        m = dict(zip(hr[ROW_ID_COL], hr[f"pred_{d}"]))
        wes[f"hist_{d}"] = wes[ROW_ID_COL].map(m)

    # conformal regime split: first 90% of TRAIN rows = fit, last 10% = cal
    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * 0.90)
    fit_mask = np.zeros(len(wes), dtype=bool)
    fit_mask[tr_pos[:cal_from]] = True
    cal_mask = np.zeros(len(wes), dtype=bool)
    cal_mask[tr_pos[cal_from:]] = True

    colsA = reg_cols()
    colsB = reg_cols() + DIST_FEATURES
    missing = [c for c in DIST_FEATURES if c not in wes.columns]
    if missing:
        raise KeyError(f"distance features absent from v3d: {missing}")

    # models: (arm, dim) -> (test preds on te positions, cal residuals)
    arm_pred = {}
    cal_res = {}
    for arm, cols in (("A", colsA), ("B", colsB)):
        Xf = prepare_matrix(wes.loc[fit_mask], cols)
        Xc = prepare_matrix(wes.loc[cal_mask], cols)
        Xt = prepare_matrix(wes.loc[te_mask], cols)
        for d in DIMENSIONS:
            yf = wes.loc[fit_mask, f"target_{d}"].to_numpy(dtype=float)
            yc = wes.loc[cal_mask, f"target_{d}"].to_numpy(dtype=float)
            pred_cal = fit_xgb(Xf, np.nan_to_num(yf), Xc, seed=SEED)
            pred_te = fit_xgb(Xf, np.nan_to_num(yf), Xt, seed=SEED)
            arm_pred[(arm, d)] = pred_te
            cal_res[(arm, d)] = np.abs(yc - pred_cal)

    # VIEWS on the test cohort (te_mask positions), labelled
    te_time = pd.to_datetime(wes.loc[te_mask, "measurement_timestamp"])
    te_dist = wes.loc[te_mask, "distance_available"].fillna(False).to_numpy().astype(bool)
    te_band = wes.loc[te_mask, "horizon_window"].to_numpy()
    views = {
        "full_test": np.ones(n_test, dtype=bool),
        "distance_present": te_dist,
        "coverage_restricted": (te_time <= LEDGER_END).to_numpy(),
    }

    # baseline evaluation per (dimension, band, view)
    out = {"task": "horizon-windowed forecast benchmark (Stage 3D)",
           "status": "diagnostic benchmark; empirical temporal coverage, not a guarantee",
           "n_train": n_train, "n_test": n_test,
           "split": "frozen chronological cohort (v3c)",
           "arms": ["A_time_state", "B_state_plus_distance"],
           "seed": SEED, "ledger_end": str(LEDGER_END),
           "baselines": {}, "ml": {}}

    for d in DIMENSIONS:
        yt = wes.loc[te_mask, f"target_{d}"].to_numpy(dtype=float)
        base = wes.loc[te_mask, f"base_{d}"].to_numpy(dtype=float)
        hist = wes.loc[te_mask, f"hist_{d}"].to_numpy(dtype=float)
        out["baselines"][d] = {}
        for band in BANDS:
            bm = te_band == band
            for view, vm in views.items():
                s = bm & vm
                out["baselines"][d][f"{band}/{view}"] = {
                    "persistence": _reg_metrics(yt[s], base[s]),
                    "historical_rate": _reg_metrics(yt[s], hist[s]),
                }

    cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()
    for (arm, d), pred in arm_pred.items():
        yt = wes.loc[te_mask, f"target_{d}"].to_numpy(dtype=float)
        out["ml"][f"arm{arm}_{d}"] = {}
        for band in BANDS:
            bm = te_band == band
            widths = {lev: conformal_width(cal_res[(arm, d)][cal_band == band], alpha)
                      for lev, alpha in NOMINAL.items()}
            out["ml"][f"arm{arm}_{d}"][band] = {"n": int(bm.sum())}
            for view, vm in views.items():
                s = bm & vm
                cell = dict(_reg_metrics(yt[s], pred[s]))
                for lev, w in widths.items():
                    cell[lev] = coverage_view(yt[s], pred[s], w)
                out["ml"][f"arm{arm}_{d}"][band][view] = cell

    # actual dt distribution per band (from v3d interval_days on test rows)
    out["dt_by_band"] = {}
    for band in BANDS:
        v = wes.loc[te_mask, "interval_days"].to_numpy()
        v = v[te_band == band]
        out["dt_by_band"][band] = {
            "n": int(v.size),
            "median": round(float(np.median(v)), 3),
            "q1": round(float(np.percentile(v, 25)), 3),
            "q3": round(float(np.percentile(v, 75)), 3),
        }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "forecast_benchmark_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()