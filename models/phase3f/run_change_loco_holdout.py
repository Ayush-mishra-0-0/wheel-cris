"""Phase 3F - grouped-by-loco change-space holdout (transferability stress).

The transferability test of Phase 3F in CHANGE space: ~20% of wheelsets are
fully held out; M4 trains on held-in train-split rows and is evaluated on the
TEST rows of never-seen wheelsets. If a degradation-dynamics gain survives on
never-seen units it is transferable, not memorized. Reported as a stress, never
a promise; failure is reported honestly.

Baselines alongside: zero-change (dX=0), per-wheelset historical rate (which by
construction is empty for never-seen wheelsets -> falls back to 0), population
drift. Conformal calibrated on held-in room slots, evaluated empirically.

Output: models/experiments/v3f/change_loco_holdout_results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3e"))
sys.path.insert(0, str(_HERE.parent / "phase3c"))

from degradation_eval import (  # noqa: E402
    DIMENSIONS, CATEGORICAL_COLUMNS, add_targets_and_bases,
    add_historical_rate_predictions,
)
from run_info_ladder import arm_columns, prepare_matrix  # noqa: E402
from run_change_space_dynamics import (  # noqa: E402
    fit_xgb_seed, conformal_width, coverage_view, NOISE_FLOOR, NOMINAL,
)

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"
SEED = 42
HOLDOUT_FRAC = 0.20
CAL_TAIL_FRAC = 0.10
BANDS = ["30d", "60d", "90d", "180d", "365d"]
ID_COL = "wheelset_equipment_id"


def reg_metrics(yt, yp):
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n < 10:
        return {"mae": np.nan, "mae_se": np.nan, "rmse": np.nan,
                "spearman": np.nan, "bias": np.nan, "var_fidelity": np.nan,
                "n": n, "n_ok": n >= 50}
    yt, yp = yt[v], yp[v]
    err = np.abs(yt - yp)
    mae = float(np.mean(err))
    se = float(np.std(err, ddof=1) / np.sqrt(n))
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    return {"mae": round(mae, 4), "mae_se": round(se, 4),
            "ci95_lo": round(mae - 1.96 * se, 4), "ci95_hi": round(mae + 1.96 * se, 4),
            "rmse": round(float(np.sqrt(np.mean((yt - yp) ** 2))), 4),
            "spearman": round(rho, 4), "bias": round(float(np.mean(yp - yt)), 4),
            "var_fidelity": round(float(np.std(yp) / np.std(yt)), 4)
            if np.std(yt) > 0 else np.nan,
            "n": n, "n_ok": n >= 50}


def sign_accuracy(yt, yp, floor):
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp) & (np.abs(yt) > floor)
    n = int(v.sum())
    if n < 10:
        return {"n": n, "sign_acc": np.nan}
    return {"n": n, "sign_acc": round(float(np.mean(np.sign(yt[v]) == np.sign(yp[v]))), 4)}


def main() -> None:
    wes = pd.read_parquet(V3F)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    rng = np.random.default_rng(SEED)
    units = np.sort(wes[ID_COL].unique())
    n_hold = int(len(units) * HOLDOUT_FRAC)
    held = set(rng.choice(units, size=n_hold, replace=False))
    ho = wes[ID_COL].isin(held).to_numpy()

    tr_mask = wes["split"].eq("train").to_numpy() & ~ho
    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * (1.0 - CAL_TAIL_FRAC))
    fit_mask = np.zeros(len(wes), dtype=bool)
    fit_mask[tr_pos[:cal_from]] = True
    cal_mask = np.zeros(len(wes), dtype=bool)
    cal_mask[tr_pos[cal_from:]] = True
    ev_mask = wes["split"].eq("test").to_numpy() & ho & wes["horizon_window"].isin(BANDS)
    ev_pos = np.where(ev_mask)[0]

    hist = add_historical_rate_predictions(wes)
    hist_dX = {}
    for d in DIMENSIONS:
        hist_dX[d] = (hist[f"pred_{d}"] - hist[f"base_{d}"]).to_numpy(dtype=float)

    # population drift trained on held-in train rows only
    tr = wes[tr_mask]
    drift = {}
    for d in DIMENSIONS:
        out = np.zeros(len(wes))
        for band in BANDS:
            sel = tr["horizon_window"] == band
            rate = (tr.loc[sel, f"dX_{d}"] / tr.loc[sel, "interval_days"]).mean()
            bm = wes["horizon_window"] == band
            out[bm] = (rate * wes.loc[bm, "interval_days"]).fillna(0.0)
        drift[d] = out

    cols = arm_columns()["M4_operational"]
    cat_list = CATEGORICAL_COLUMNS
    Xf = prepare_matrix(wes.loc[fit_mask], cols, cat_list)
    Xc = prepare_matrix(wes.loc[cal_mask], cols, cat_list)
    Xe = prepare_matrix(wes.loc[ev_pos], cols, cat_list)
    band_ev = wes.loc[ev_pos, "horizon_window"].to_numpy()
    cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()

    out = {
        "task": "grouped-by-loco change-space holdout (Stage 3F transferability stress)",
        "status": "stress; ~20% of wheelsets fully held out; reported as a stress, not a benchmark",
        "n_unit_total": int(len(units)), "n_unit_holdout": int(n_hold),
        "n_fit": int(fit_mask.sum()), "n_cal": int(cal_mask.sum()),
        "n_heldout_test_eval": int(len(ev_pos)),
        "split_discipline": "test-split rows of held-out wheelsets only",
        "target": "dX_d = target_d - base_d",
        "seed": SEED,
        "by_dim_band": {},
    }

    for d in DIMENSIONS:
        yf = wes.loc[fit_mask, f"dX_{d}"].to_numpy(dtype=float)
        yc = wes.loc[cal_mask, f"dX_{d}"].to_numpy(dtype=float)
        pred_cal = fit_xgb_seed(Xf, yf, Xc)
        pred_ev = fit_xgb_seed(Xf, yf, Xe)
        yt = wes.loc[ev_pos, f"dX_{d}"].to_numpy(dtype=float)
        resid = np.abs(yc - pred_cal)
        out["by_dim_band"][d] = {}
        for band in BANDS:
            bm = band_ev == band
            widths = {lev: conformal_width(resid[cal_band == band], alpha)
                      for lev, alpha in NOMINAL.items()}
            cell = {
                "n": int(bm.sum()),
                "zero_change": reg_metrics(yt[bm], np.zeros(bm.sum())),
                "population_drift": reg_metrics(yt[bm], drift[d][ev_pos][bm]),
                "historical_rate": reg_metrics(yt[bm], hist_dX[d][ev_pos][bm]),
                "M4": reg_metrics(yt[bm], pred_ev[bm]),
            }
            cell["M4"]["sign_acc"] = sign_accuracy(
                yt[bm], pred_ev[bm], NOISE_FLOOR[d])["sign_acc"]
            for lev, w in widths.items():
                cell[lev] = coverage_view(yt[bm], pred_ev[bm], w)
            out["by_dim_band"][d][band] = cell

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "change_loco_holdout_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("loco holdout:", n_hold, "units;", int(len(ev_pos)), "held-out test rows")


if __name__ == "__main__":
    main()
