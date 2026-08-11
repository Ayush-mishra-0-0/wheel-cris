"""Phase 3F - rolling change-space production simulation (PRIMARY evidence).

Simulates a monthly-rescore deployment in CHANGE space. At each refit date t0
the model trains ONLY on train-split rows with measurement time <= t0
(point-in-time, no future facts) and is evaluated on rows measured in the
following EVAL_HORIZON_DAYS. Target is dX_d = target_d - base_d (mm); the
zero-change baseline (dX=0) and the per-wheelset historical rate are reported
alongside M4 for every month.

Per docs/phase3f_plan.md the rolling simulation is the PRIMARY deployment
evidence; the grouped-by-loco holdout is a stress test. Conformal calibration
uses the last 10% of the chronological training prefix at each refit; coverage
is reported as EMPIRICAL temporal coverage (observed diagnostic).

Output: models/experiments/v3f/rolling_change_sim_results.json
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
    DIMENSIONS, add_targets_and_bases, add_historical_rate_predictions,
)
from run_info_ladder import arm_columns, prepare_matrix  # noqa: E402
from run_change_space_dynamics import (  # noqa: E402
    fit_xgb_seed, conformal_width, coverage_view, NOISE_FLOOR, NOMINAL,
)

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"

from xgboost import XGBRegressor  # noqa: E402

SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")
BANDS = ["30d", "60d", "90d", "180d", "365d"]
EVAL_HORIZON_DAYS = 90
MIN_TRAIN_ROWS = 10000


def _fit_xgb_model(Xtr, ytr, seed=SEED):
    ytr = np.asarray(ytr, dtype=float)
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return None
    m = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                     subsample=1.0, colsample_bytree=1.0, random_state=seed,
                     n_jobs=-1, tree_method="hist")
    m.fit(Xtr[fin], ytr[fin])
    return m


def reg_metrics(yt, yp):
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n < 10:
        return {"mae": np.nan, "rmse": np.nan, "spearman": np.nan,
                "bias": np.nan, "var_fidelity": np.nan, "n": n}
    yt, yp = yt[v], yp[v]
    mae = float(np.mean(np.abs(yt - yp)))
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    return {"mae": round(mae, 4), "rmse": round(float(np.sqrt(np.mean((yt - yp) ** 2))), 4),
            "spearman": round(rho, 4), "bias": round(float(np.mean(yp - yt)), 4),
            "var_fidelity": round(float(np.std(yp) / np.std(yt)), 4)
            if np.std(yt) > 0 else np.nan, "n": n}


def sign_accuracy(yt, yp, floor):
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp) & (np.abs(yt) > floor)
    n = int(v.sum())
    if n < 10:
        return np.nan
    return round(float(np.mean(np.sign(yt[v]) == np.sign(yp[v]))), 4)


def main() -> None:
    wes = pd.read_parquet(V3F)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)
    wes["time"] = pd.to_datetime(wes["measurement_timestamp"])
    wes["month"] = wes["time"].dt.to_period("M")
    tr_only = (wes["split"] == "train").to_numpy()

    hist = add_historical_rate_predictions(wes)
    hist_dX = {}
    for d in DIMENSIONS:
        hist_dX[d] = (hist[f"pred_{d}"] - hist[f"base_{d}"]).to_numpy(dtype=float)

    cols = arm_columns()["M4_operational"]
    cat_list = None  # prepare_matrix signature uses cats list; we import it below

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
    refit_months = [m for m in all_months if first_refit <= m <= stop_month]

    # import the categoricals from the info-ladder module at runtime
    from degradation_eval import CATEGORICAL_COLUMNS  # noqa: E402
    cat_list = CATEGORICAL_COLUMNS

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
        cal_from = int(len(tr_pos) * (1.0 - 0.10))
        fit_mask = np.zeros(len(wes), dtype=bool)
        fit_mask[tr_pos[:cal_from]] = True
        cal_mask = np.zeros(len(wes), dtype=bool)
        cal_mask[tr_pos[cal_from:]] = True
        ev_pos = np.where(ev_mask)[0]

        Xf = prepare_matrix(wes.loc[fit_mask], cols, cat_list)
        Xc = prepare_matrix(wes.loc[cal_mask], cols, cat_list)
        Xe = prepare_matrix(wes.loc[ev_pos], cols, cat_list)
        band_ev = wes.loc[ev_pos, "horizon_window"].to_numpy()
        cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()

        sim[str(m)] = {"refit": str(t0), "n_train_fit": int(fit_mask.sum()),
                       "n_cal": int(cal_mask.sum()), "n_eval": int(len(ev_pos))}
        for d in DIMENSIONS:
            yf = wes.loc[fit_mask, f"dX_{d}"].to_numpy(dtype=float)
            yc = wes.loc[cal_mask, f"dX_{d}"].to_numpy(dtype=float)
            model = _fit_xgb_model(Xf, yf)  # fit ONCE per dim; reuse for cal+eval
            pred_cal = model.predict(Xc)
            pred_ev = model.predict(Xe)
            yt = wes.loc[ev_pos, f"dX_{d}"].to_numpy(dtype=float)
            resid = np.abs(yc - pred_cal)
            sim[str(m)][d] = {}
            for band in BANDS:
                bm = band_ev == band
                widths = {lev: conformal_width(resid[cal_band == band], alpha)
                          for lev, alpha in NOMINAL.items()}
                cell = {
                    "n": int(bm.sum()),
                    "zero_change": reg_metrics(yt[bm], np.zeros(bm.sum())),
                    "historical_rate": reg_metrics(yt[bm], hist_dX[d][ev_pos][bm]),
                    "M4": reg_metrics(yt[bm], pred_ev[bm]),
                }
                cell["M4"]["sign_acc"] = sign_accuracy(
                    yt[bm], pred_ev[bm], NOISE_FLOOR[d])
                for lev, w in widths.items():
                    cell[lev] = coverage_view(yt[bm], pred_ev[bm], w)
                sim[str(m)][d][band] = cell

    # monthly-aggregate (mean across refits) per dim/band
    agg = {d: {b: {"zero_change_mae": [], "hist_mae": [], "M4_mae": [],
                    "M4_rho": [], "M4_var_fid": [], "M4_sign": [],
                    "i80_cov": [], "i95_cov": [], "n": []}
               for b in BANDS} for d in DIMENSIONS}
    for m, cell_m in sim.items():
        for d in DIMENSIONS:
            for b in BANDS:
                c = cell_m[d][b]
                a = agg[d][b]
                a["n"].append(c["n"])
                a["zero_change_mae"].append(c["zero_change"]["mae"])
                a["hist_mae"].append(c["historical_rate"]["mae"])
                a["M4_mae"].append(c["M4"]["mae"])
                a["M4_rho"].append(c["M4"]["spearman"])
                a["M4_var_fid"].append(c["M4"]["var_fidelity"])
                a["M4_sign"].append(c["M4"].get("sign_acc"))
                a["i80_cov"].append(c["i80"]["empirical_coverage"]
                                    if c["i80"].get("empirical_coverage") is not None else np.nan)
                a["i95_cov"].append(c["i95"]["empirical_coverage"]
                                    if c["i95"].get("empirical_coverage") is not None else np.nan)

    def _mean(v):
        v = np.asarray([x for x in v if x is not None and x == x], dtype=float)
        return round(float(v.mean()), 4) if v.size else None

    summary = {}
    for d in DIMENSIONS:
        summary[d] = {}
        for b in BANDS:
            a = agg[d][b]
            summary[d][b] = {
                "months": len(a["n"]),
                "total_n": int(np.sum(a["n"])),
                "zero_change_mae_mean": _mean(a["zero_change_mae"]),
                "hist_mae_mean": _mean(a["hist_mae"]),
                "M4_mae_mean": _mean(a["M4_mae"]),
                "M4_rho_mean": _mean(a["M4_rho"]),
                "M4_var_fid_mean": _mean(a["M4_var_fid"]),
                "M4_sign_mean": _mean(a["M4_sign"]),
                "i80_cov_mean": _mean(a["i80_cov"]),
                "i95_cov_mean": _mean(a["i95_cov"]),
            }

    results = {
        "task": "rolling change-space production simulation (Stage 3F, PRIMARY)",
        "status": "chronological refit; point-in-time only; empirical temporal coverage",
        "seed": SEED, "ledger_end": str(LEDGER_END),
        "split_discipline": "train-split rows only; frozen cohort respected",
        "target": "dX_d = target_d - base_d",
        "refit_months": list(sim.keys()),
        "monthly_summary": summary,
        "sim": sim,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "rolling_change_sim_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("rolled months:", len(sim), str(OUTPUT.relative_to(ROOT)))


if __name__ == "__main__":
    main()
