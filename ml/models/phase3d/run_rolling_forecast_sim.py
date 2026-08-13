"""Phase 3D - rolling production simulation (primary deployment evidence).

Simulates a monthly-rescore deployment: at each refit date we train ONLY on
rows whose measurement time <= refit time (point-in-time, no future facts) and
evaluate on rows measured in the following EVAL_HORIZON_DAYS (1-3 months).
Per docs/phase3d_plan.md the rolling simulation is the PRIMARY deployment
evidence; the grouped-by-loco holdout is a stress test.

The frozen chronological cohort remains the discipline: only TRAIN-split rows
may ever enter training. Forecast evaluation uses only rows in one of the five
forecast bands (never the 'other' band). Split conformal calibration uses the
last 10% of the chronological training prefix at each refit. Coverage is
reported as EMPIRICAL temporal coverage (observed diagnostic).

Output: models/experiments/v3d/rolling_forecast_sim_results.json
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

from degradation_eval import ROW_ID_COL, DIMENSIONS, add_targets_and_bases  # noqa: E402
from degradation_eval import add_historical_rate_predictions  # noqa: E402
from degradation_eval import fit_xgb, _reg_metrics  # noqa: E402

from run_forecast_benchmark import (  # noqa: E402
    reg_cols, prepare_matrix, conformal_width, coverage_view, NOMINAL,
    DIST_FEATURES,
)

ROOT = Path(__file__).resolve().parents[2]
V3D = ROOT / "model_datasets" / "v3d" / "forecast_horizon_benchmark_pairs.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3d"
SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")

BANDS = ["30d", "60d", "90d", "180d", "365d"]
EVAL_HORIZON_DAYS = 90
MIN_TRAIN_ROWS = 10000
CAL_TAIL_FRAC = 0.10


def main() -> None:
    wes = pd.read_parquet(V3D)
    wes = add_targets_and_bases(wes)  # idempotent
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)
    wes["time"] = pd.to_datetime(wes["measurement_timestamp"])
    wes["month"] = wes["time"].dt.to_period("M")
    tr_only = (wes["split"] == "train").to_numpy()

    # historical-rate trajectory baseline (point-in-time per wheelset)
    hist = add_historical_rate_predictions(wes)
    for d in DIMENSIONS:
        m = dict(zip(hist[ROW_ID_COL], hist[f"pred_{d}"]))
        wes[f"hist_{d}"] = wes[ROW_ID_COL].map(m)

    cols = reg_cols() + ["interval_distance_km", "distance_per_day_km",
                         "rtis_distance_coverage_pct_in_interval",
                         "distance_since_turning_km", "distance_available"]
    missing = [c for c in DIST_FEATURES if c not in wes.columns]
    if missing:
        raise KeyError(f"missing features in v3d: {missing}")

    # refit grid: every calendar month from first month with >= MIN_TRAIN_ROWS
    all_months = sorted(wes["month"].unique())
    cum = 0
    first_refit = None
    for m in all_months:
        cum += int(((wes["month"] == m) & tr_only).sum())
        if cum >= MIN_TRAIN_ROWS:
            first_refit = m
            break
    if first_refit is None:
        raise RuntimeError("never reached MIN_TRAIN_ROWS train rows")

    stop_month = pd.Period(LEDGER_END, freq="M")
    refit_months = [m for m in all_months
                    if first_refit <= m <= stop_month]

    sim = {}
    for m in refit_months:
        t0 = m.start_time
        t1 = t0 + pd.Timedelta(days=EVAL_HORIZON_DAYS)
        train_mask = tr_only & (wes["time"] <= t0)
        ev_mask = (wes["time"] > t0) & (wes["time"] <= t1) \
            & wes["horizon_window"].isin(BANDS)
        if int(train_mask.sum()) < MIN_TRAIN_ROWS:
            continue

        tr_pos = np.where(train_mask)[0]
        cal_from = int(len(tr_pos) * (1.0 - CAL_TAIL_FRAC))
        fit_mask = np.zeros(len(wes), dtype=bool)
        fit_mask[tr_pos[:cal_from]] = True
        cal_mask = np.zeros(len(wes), dtype=bool)
        cal_mask[tr_pos[cal_from:]] = True
        ev_pos = np.where(ev_mask)[0]

        Xf = prepare_matrix(wes.loc[fit_mask], cols)
        Xc = prepare_matrix(wes.loc[cal_mask], cols)
        Xe = prepare_matrix(wes.loc[ev_pos], cols)
        band_ev = wes.loc[ev_pos, "horizon_window"].to_numpy()
        cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()

        sim[str(m)] = {"refit": str(t0), "n_train_fit": int(fit_mask.sum()),
                       "n_cal": int(cal_mask.sum()), "n_eval": int(len(ev_pos))}
        for d in DIMENSIONS:
            yf = wes.loc[fit_mask, f"target_{d}"].to_numpy(dtype=float)
            yc = wes.loc[cal_mask, f"target_{d}"].to_numpy(dtype=float)
            pred_cal = fit_xgb(Xf, np.nan_to_num(yf), Xc, seed=SEED)
            pred_ev = fit_xgb(Xf, np.nan_to_num(yf), Xe, seed=SEED)
            yt = wes.loc[ev_pos, f"target_{d}"].to_numpy(dtype=float)
            base = wes.loc[ev_pos, f"base_{d}"].to_numpy(dtype=float)
            hr = wes.loc[ev_pos, f"hist_{d}"].to_numpy(dtype=float)
            resid = np.abs(yc - pred_cal)
            sim[str(m)][d] = {}
            for band in BANDS:
                bm = band_ev == band
                widths = {lev: conformal_width(resid[cal_band == band], alpha)
                          for lev, alpha in NOMINAL.items()}
                cell = {
                    "n_total": int(bm.sum()),
                    "persistence": _reg_metrics(yt[bm], base[bm]),
                    "historical_rate": _reg_metrics(yt[bm], hr[bm]),
                    "xgb": _reg_metrics(yt[bm], pred_ev[bm]),
                }
                for lev, w in widths.items():
                    cell[lev] = coverage_view(yt[bm], pred_ev[bm], w)
                sim[str(m)][d][band] = cell

    results = {
        "task": "rolling production simulation (Stage 3D, primary evidence)",
        "status": "chronological refit; point-in-time only; empirical temporal coverage",
        "seed": SEED, "ledger_end": str(LEDGER_END),
        "split_discipline": "train-split rows only; frozen cohort respected",
        "refit_months": list(sim.keys()),
        "sim": sim,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "rolling_forecast_sim_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("rolled months:", len(sim), str(OUTPUT.relative_to(ROOT)))


if __name__ == "__main__":
    main()