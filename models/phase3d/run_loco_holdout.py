"""Phase 3D - grouped-by-locomotive holdout (generalization stress test).

Per docs/phase3d_plan.md this is a STRESS TEST, not the primary benchmark:
a ~20% subset of wheelsets is held out entirely from training, and the model is
evaluated on those never-seen locomotives across every forecast band. It proves
whether the model generalizes BEYOND seen locomotives; a failure to generalize
is reported as such, never hidden.

Design:
  * Hold out by wheelset_equipment_id (stable, ~20% via intraclass hash).
  * Train Arm B (state+distance) on the remaining train-split rows.
  * Evaluate on ALL rows of the held-out locomotives (train+test split IDs are
    still respected for comparison vs persistence — we evaluate the frozen test
    rows of held-out locos, plus report the same on held-out locos' train-era
    rows only when they exist; the headline number is the held-out test rows).
  * Per (dimension, band): MAE/RMSE/R2/Spearman vs persistence, and empirical
    temporal coverage (split conformal calibrated on held-in room slots).

This is a diagnostic stress test. Coverage is empirical temporal coverage, not a
guarantee.

Output: models/experiments/v3d/loco_holdout_results.json
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
    ROW_ID_COL, DIMENSIONS, add_targets_and_bases, add_historical_rate_predictions,
    fit_xgb, _reg_metrics,
)
from run_forecast_benchmark import (  # noqa: E402
    reg_cols, prepare_matrix, conformal_width, coverage_view, NOMINAL, DIST_FEATURES,
)

ROOT = Path(__file__).resolve().parents[2]
V3D = ROOT / "model_datasets" / "v3d" / "forecast_horizon_benchmark_pairs.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3d"
SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")
HOLDOUT_FRAC = 0.20
CAL_TAIL_FRAC = 0.10

BANDS = ["30d", "60d", "90d", "180d", "365d"]


def main() -> None:
    wes = pd.read_parquet(V3D)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    rng = np.random.default_rng(SEED)
    locos = np.sort(wes["wheelset_equipment_id"].unique())
    n_hold = int(len(locos) * HOLDOUT_FRAC)
    holdout_ids = set(rng.choice(locos, size=n_hold, replace=False))
    ho = wes["wheelset_equipment_id"].isin(holdout_ids).to_numpy()

    # training = non-held-out locos, train-split only
    tr_mask = wes["split"].eq("train").to_numpy() & ~ho
    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * (1.0 - CAL_TAIL_FRAC))
    fit_mask = np.zeros(len(wes), dtype=bool)
    fit_mask[tr_pos[:cal_from]] = True
    cal_mask = np.zeros(len(wes), dtype=bool)
    cal_mask[tr_pos[cal_from:]] = True
    # evaluation = held-out locos' test rows (frozen test cohort discipline)
    ev_mask = wes["split"].eq("test").to_numpy() & ho & wes["horizon_window"].isin(BANDS)
    ev_pos = np.where(ev_mask)[0]

    hist = add_historical_rate_predictions(wes)
    for d in DIMENSIONS:
        m = dict(zip(hist[ROW_ID_COL], hist[f"pred_{d}"]))
        wes[f"hist_{d}"] = wes[ROW_ID_COL].map(m)

    cols = reg_cols() + DIST_FEATURES
    missing = [c for c in DIST_FEATURES if c not in wes.columns]
    if missing:
        raise KeyError(f"missing features in v3d: {missing}")

    Xf = prepare_matrix(wes.loc[fit_mask], cols)
    Xc = prepare_matrix(wes.loc[cal_mask], cols)
    Xe = prepare_matrix(wes.loc[ev_pos], cols)
    band_ev = wes.loc[ev_pos, "horizon_window"].to_numpy()
    cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()

    out = {
        "task": "grouped-by-loco holdout (Stage 3D stress test)",
        "status": "stress; ~20% of locomotives fully held out; reported as a stress, not a benchmark",
        "n_loco_total": int(len(locos)), "n_loco_holdout": int(n_hold),
        "n_fit": int(fit_mask.sum()), "n_cal": int(cal_mask.sum()),
        "n_heldout_test_eval": int(len(ev_pos)),
        "split_discipline": "test-split rows of held-out locomotives only",
        "seed": SEED,
    }
    out["by_dim_band"] = {}
    for d in DIMENSIONS:
        yf = wes.loc[fit_mask, f"target_{d}"].to_numpy(dtype=float)
        yc = wes.loc[cal_mask, f"target_{d}"].to_numpy(dtype=float)
        pred_cal = fit_xgb(Xf, np.nan_to_num(yf), Xc, seed=SEED)
        pred_ev = fit_xgb(Xf, np.nan_to_num(yf), Xe, seed=SEED)
        yt = wes.loc[ev_pos, f"target_{d}"].to_numpy(dtype=float)
        base = wes.loc[ev_pos, f"base_{d}"].to_numpy(dtype=float)
        hr = wes.loc[ev_pos, f"hist_{d}"].to_numpy(dtype=float)
        resid = np.abs(yc - pred_cal)
        out["by_dim_band"][d] = {}
        for band in BANDS:
            bm = band_ev == band
            widths = {lev: conformal_width(resid[cal_band == band], alpha)
                      for lev, alpha in NOMINAL.items()}
            cell = {
                "n": int(bm.sum()),
                "persistence": _reg_metrics(yt[bm], base[bm]),
                "historical_rate": _reg_metrics(yt[bm], hr[bm]),
                "xgb": _reg_metrics(yt[bm], pred_ev[bm]),
            }
            for lev, w in widths.items():
                cell[lev] = coverage_view(yt[bm], pred_ev[bm], w)
            out["by_dim_band"][d][band] = cell

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "loco_holdout_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("loco holdout:", n_hold, "locos;", int(len(ev_pos)), "held-out test rows")


if __name__ == "__main__":
    main()