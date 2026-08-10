"""Phase 3E - information ladder: does history matter, and whose?

Same rows, same frozen split, same seeds/hyperparameters. Only the information
placed into the model differs. Nested ladder so any metric delta is attributable
to the newly allowed family:

  M0   persistence / historical-rate baselines (no model)
  M1   current state + horizon           (S_t, quality, actual interval_days)
  M2   M1 + trajectory history           (30/90/180d deltas, rates, inspection)
  M3   M2 + exposure/distance history    (trailing km windows + availability)
  M4   M3 + operational / loco context   (loco, wheel, shed, defect, position)
  M5   M4 + track data                   NOT AVAILABLE in this corpus

Every arm is the same XGBoost per (dimension) predicting the next measured
absolute state with interval_days as a continuous feature; evaluation is per
horizon band. Coverage = split conformal (calibration = last 10% of TRAIN
rows), reported as EMPIRICAL TEMPORAL COVERAGE on four labelled views:
full_test, distance_present, distance-missing, coverage_restricted.

Note: rate_per_1000km features themselves embed distance history, so they live
in M2 per the trajectory spec, and the standalone distance-frame aggregates
(km_last_30d/90d/180d + availability) enter in M3.

Truly no track data exists in this corpus. M5 is reported as "not evaluated -
no track table (absence documented, consistent with the environment)".
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

import sys
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3c"))
sys.path.insert(0, str(_HERE.parent / "phase3d"))

from degradation_eval import (  # noqa: E402
    DIMENSIONS, STATE_COLUMNS, QUALITY_COLUMNS, CATEGORICAL_COLUMNS,
    add_targets_and_bases,
)
from run_forecast_benchmark import (  # noqa: E402
    conformal_width, coverage_view, NOMINAL, LEDGER_END,
)

ROOT = Path(__file__).resolve().parents[2]
V3E = ROOT / "model_datasets" / "v3e" / "forecast_information_ladder.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3e"
SEED = 42
BANDS = ["30d", "60d", "90d", "180d", "365d"]
TRAJ_WINDOWS = [30, 90, 180]

MAINTENANCE_COLS = [
    "maintenance_jobcard_creation_count", "rtis_source_event_count",
    "rtis_source_event_type_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
]
LIFECYCLE_COLS = ["days_since_turning", "wheel_age_days_proxy"]


def arm_columns() -> dict:
    traj_rate, dist_hist = [], []
    for Wd in TRAJ_WINDOWS:
        traj_rate.append(f"inspection_count_{Wd}d")
        dist_hist += [f"km_last_{Wd}d", f"km_{Wd}d_available"]
        for d in DIMENSIONS:
            traj_rate += [f"{d}_change_last_{Wd}d",
                          f"{d}_rate_per_day_{Wd}d",
                          f"{d}_rate_per_1000km_{Wd}d"]
    traj_rate += ["days_since_last_inspection"]
    m1 = (STATE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]
          + ["interval_days", "horizon_days"] + LIFECYCLE_COLS)
    return {
        "M1_state": sorted(m1),
        "M2_trajectory": sorted(m1 + traj_rate),
        "M3_exposure": sorted(m1 + traj_rate + dist_hist),
        "M4_operational": sorted(m1 + traj_rate + dist_hist
                                 + CATEGORICAL_COLUMNS + MAINTENANCE_COLS),
    }


def dist_flag_cols() -> list[str]:
    return [f"km_{Wd}d_available" for Wd in TRAJ_WINDOWS]


def prepare_matrix(wear: pd.DataFrame, num_cols: list[str], cats: list[str]) -> np.ndarray:
    enc = wear.copy()
    code_map = {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
                "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}
    for q in QUALITY_COLUMNS:
        enc[q + "_code"] = enc[q].fillna("MISSING").map(code_map).astype(float)
    enc[num_cols] = enc[num_cols].replace({pd.NA: np.nan, pd.NaT: np.nan})
    for c in cats:
        vals = sorted(enc[c].dropna().astype(str).unique())
        code = {v: i for i, v in enumerate(vals)}
        enc[c] = enc[c].astype(str).map(code).astype(float).fillna(-1.0)
    M = enc[num_cols].astype(float).fillna(0.0)
    for c in dist_flag_cols():
        if c in M.columns:
            M[c] = M[c].fillna(0.0)
    return M.to_numpy().astype(np.float64)


def fit_xgb_seed(Xtr, ytr, Xte, seed=SEED):
    ytr = np.asarray(ytr, dtype=float)
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return np.full(Xte.shape[0], np.nan)
    m = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                     subsample=1.0, colsample_bytree=1.0, random_state=seed,
                     n_jobs=-1, tree_method="hist")
    m.fit(Xtr[fin], ytr[fin])
    return m.predict(Xte)


def reg_metrics(yt, yp) -> dict:
    yt = np.asarray(yt, dtype=float)
    yf = np.asarray(yp, dtype=float)
    valid = np.isfinite(yt) & np.isfinite(yp)
    n = int(valid.sum())
    if n < 10:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "spearman": np.nan, "n": n}
    yt, yf = yt[valid], yf[valid]
    mae = float(np.mean(np.abs(yt - yf)))
    rmse = float(np.sqrt(np.mean((yt - yf) ** 2)))
    ss_res = float(np.sum((yt - yf) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rho = np.nan if np.all(yf == yf[0]) else float(spearmanr(yt, yf)[0])
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4),
            "spearman": round(rho, 4), "n": n}


def main() -> None:
    wes = pd.read_parquet(V3E)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    tr_mask = (wes["split"] == "train").to_numpy()
    te_mask = (wes["split"] == "test").to_numpy()
    n_train, n_test = int(tr_mask.sum()), int(te_mask.sum())

    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * 0.90)
    fit_mask = np.zeros(len(wes), dtype=bool)
    fit_mask[tr_pos[:cal_from]] = True
    cal_mask = np.zeros(len(wes), dtype=bool)
    cal_mask[tr_pos[cal_from:]] = True

    arms = arm_columns()
    cat_list = CATEGORICAL_COLUMNS
    te_band = wes.loc[te_mask, "horizon_window"].to_numpy()
    te_time = pd.to_datetime(wes.loc[te_mask, "measurement_timestamp"])
    te_dist = wes.loc[te_mask, "distance_available"].fillna(False).to_numpy().astype(bool)
    views = {
        "full_test": np.ones(n_test, dtype=bool),
        "distance_present": te_dist,
        "distance_missing": ~te_dist,
        "coverage_restricted": (te_time <= LEDGER_END).to_numpy(),
    }

    out = {
        "task": "information ladder (Stage 3E)",
        "status": "nested assembled delta; empirical temporal coverage, not a guarantee",
        "n_train": n_train, "n_test": n_test,
        "split": "frozen chronological cohort (v3c)",
        "arms": list(arm_columns().keys()) + ["M5_track"],
        "seed": SEED, "ledger_end": str(LEDGER_END),
        "note_m5": "M5 (M4 + track data) NOT EVALUATED: no track table exists in "
                   "this corpus; consistent with the environment. No claim made.",
        "ml": {}, "dt_by_band": {},
    }

    # baselines (M0) per dimension / band / view
    for d in DIMENSIONS:
        dmap = out["ml"][f"M0_persistence_{d}"] = {}
        yt = wes.loc[te_mask, f"target_{d}"].to_numpy(dtype=float)
        base = wes.loc[te_mask, f"base_{d}"].to_numpy(dtype=float)
        for band in BANDS:
            inb = te_band == band
            dmap[band] = {}
            for view, vm in views.items():
                s = inb & vm
                dmap[band][view] = {"persistence": reg_metrics(yt[s], base[s])}

    arms = arm_columns()
    cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()

    for arm, cols in arms.items():
        Xf = prepare_matrix(wes.loc[fit_mask], cols, cat_list)
        Xc = prepare_matrix(wes.loc[cal_mask], cols, cat_list)
        Xt = prepare_matrix(wes.loc[te_mask], cols, cat_list)
        for d in DIMENSIONS:
            yf = wes.loc[fit_mask, f"target_{d}"].to_numpy(dtype=float)
            yc = wes.loc[cal_mask, f"target_{d}"].to_numpy(dtype=float)
            pred_te = fit_xgb_seed(Xf, yf, Xt)
            pred_cal = fit_xgb_seed(Xf, yf, Xc)
            yt = wes.loc[te_mask, f"target_{d}"].to_numpy(dtype=float)
            cell = out["ml"][f"{arm}_{d}"] = {}
            for band in BANDS:
                inb = te_band == band
                widths = {
                    lev: conformal_width(
                        np.abs(yc - pred_cal)[cal_band == band], alpha)
                    for lev, alpha in NOMINAL.items()
                }
                cell[band] = {"n": int(inb.sum())}
                for view, vm in views.items():
                    s = inb & vm
                    m = reg_metrics(yt[s], pred_te[s])
                    for lev, w in widths.items():
                        m[lev] = coverage_view(yt[s], pred_te[s], w)
                    cell[band][view] = m

    # actual dt window stats (test rows only)
    for band in BANDS:
        v = wes.loc[te_mask, "interval_days"].to_numpy()
        v = v[te_band == band]
        out["dt_by_band"][band] = {
            "n": int(v.size),
            "median": round(float(np.median(v)), 3) if v.size else np.nan,
            "q1": round(float(np.percentile(v, 25)), 3) if v.size else np.nan,
            "q3": round(float(np.percentile(v, 75)), 3) if v.size else np.nan,
        }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "information_ladder_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
