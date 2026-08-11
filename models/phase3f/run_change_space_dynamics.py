"""Phase 3F - change-space degradation-dynamics benchmark (frozen split).

Target is the CHANGE dX_d = target_d - base_d (mm), per dimension. Persistence
in this frame is dX = 0, so the model must earn every point of accuracy.

Baselines (all reported, none optional):
  B0 zero-change          dX = 0
  B1 population drift     per (dim, band) train mean rate scaled by interval_days
  B2 historical rate      per-wheelset point-in-time cumulative dX/day * interval_days

Model arms (same rows / splits / seeds / HP; predicting dX directly):
  M3 trajectory           state + quality + lifecycle + trajectory + distance hist
  M4 +operational         M3 + categoricals + maintenance/RTIS counts (3E winner)

Diagnostics per (dim, band, view, model):
  MAE / RMSE / R2 / Spearman on dX; signed bias; sign accuracy on meaningful
  change; variance fidelity std(pred)/std(obs); horizon scaling mean|pred|;
  exposure scaling Spearman(pred, km) vs Spearman(obs, km).

Conformal: split conformal on dX residuals, calibration = last 10% of
chronological TRAIN rows (never test). Reported as EMPIRICAL TEMPORAL COVERAGE.

Output: models/experiments/v3f/change_space_dynamics_results.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3e"))
sys.path.insert(0, str(_HERE.parent / "phase3c"))

from degradation_eval import (  # noqa: E402
    DIMENSIONS, QUALITY_COLUMNS, CATEGORICAL_COLUMNS, add_targets_and_bases,
    add_historical_rate_predictions,
)
from run_info_ladder import arm_columns, prepare_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"
SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")
BANDS = ["30d", "60d", "90d", "180d", "365d"]
NOMINAL = {"i80": 0.20, "i95": 0.05}

# measurement-noise floors (mm): |dX| below this is not a meaningful change.
NOISE_FLOOR = {"wsmDia": 1.0, "wsmFlangeThickness": 0.10,
               "wsmRoot": 0.10, "wsmWheelGauge": 0.05}


def reg_metrics(yt: np.ndarray, yp: np.ndarray) -> dict:
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n < 10:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "spearman": np.nan,
                "bias": np.nan, "sign_acc": np.nan, "var_fidelity": np.nan,
                "mean_abs_pred": np.nan, "mean_abs_obs": np.nan,
                "spearman_km": np.nan, "spearman_obs_km": np.nan, "n": n}
    yt, yp = yt[v], yp[v]
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4),
            "spearman": round(rho, 4), "bias": round(float(np.mean(yp - yt)), 4),
            "mean_abs_pred": round(float(np.mean(np.abs(yp))), 4),
            "mean_abs_obs": round(float(np.mean(np.abs(yt))), 4),
            "var_fidelity": round(float(np.std(yp) / np.std(yt)), 4)
            if np.std(yt) > 0 else np.nan,
            "n": n}


def sign_accuracy(yt: np.ndarray, yp: np.ndarray, floor: float) -> dict:
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp) & (np.abs(yt) > floor)
    n = int(v.sum())
    if n < 10:
        return {"n": n, "sign_acc": np.nan}
    agree = float(np.mean(np.sign(yt[v]) == np.sign(yp[v])))
    return {"n": n, "sign_acc": round(agree, 4)}


def conformal_width(resid: np.ndarray, alpha: float) -> float | None:
    s = np.asarray(resid, dtype=float)
    s = s[np.isfinite(s)]
    if s.size < 10:
        return None
    k = int(np.ceil((s.size + 1) * (1.0 - alpha)))
    k = min(max(k, 1), s.size)
    return float(np.partition(s, k - 1)[k - 1])


def coverage_view(yt: np.ndarray, yp: np.ndarray, width: float | None) -> dict:
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n == 0:
        return {"n": 0}
    if width is None:
        return {"n": n, "empirical_coverage": None, "mean_width": None}
    hit = int(np.sum(np.abs(yt[v] - yp[v]) <= width))
    return {"n": n, "empirical_coverage": round(hit / n, 4),
            "mean_width": round(float(width), 4)}


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


def population_drift_baseline(wes: pd.DataFrame) -> np.ndarray:
    """Per (dim, band) train mean dX/day rate; scaled by each row's interval."""
    pred = {}
    tr = wes[wes["split"] == "train"]
    for d in DIMENSIONS:
        out = np.zeros(len(wes))
        for band in BANDS:
            sel = (wes["split"] == "train") & (wes["horizon_window"] == band)
            rate = (tr.loc[sel, f"dX_{d}"] / tr.loc[sel, "interval_days"]).mean()
            bm = wes["horizon_window"] == band
            out[bm] = (rate * wes.loc[bm, "interval_days"]).fillna(0.0)
        pred[d] = out
    return pred


def main() -> None:
    wes = pd.read_parquet(V3F)
    wes = add_targets_and_bases(wes)  # idempotent; supplies base_/target_ cols
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

    # B2 historical-rate baseline (per-wheelset point-in-time) from 3C core
    hr = add_historical_rate_predictions(wes)
    hist_dX = {}
    for d in DIMENSIONS:
        hist_dX[d] = (hr[f"pred_{d}"] - hr[f"base_{d}"]).to_numpy(dtype=float)

    B1 = population_drift_baseline(wes)

    arms = arm_columns()
    cat_list = CATEGORICAL_COLUMNS
    arm_names = {"M3_exposure": "M3_trajectory", "M4_operational": "M4_operational"}
    model_arms = [k for k in arm_names]
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
        "task": "change-space degradation-dynamics benchmark (Stage 3F, frozen split)",
        "status": "target = dX; persistence = 0; empirical temporal coverage, not a guarantee",
        "n_train": n_train, "n_test": n_test,
        "split": "frozen chronological cohort (v3c)",
        "baselines": ["B0_zero_change", "B1_population_drift", "B2_historical_rate"],
        "model_arms": model_arms,
        "noise_floor_mm": NOISE_FLOOR,
        "seed": SEED, "ledger_end": str(LEDGER_END),
        "results": {},
    }

    # baselines + model preds per (dim) on test positions
    dX_true = {d: wes.loc[te_mask, f"dX_{d}"].to_numpy(dtype=float) for d in DIMENSIONS}
    preds = {("B0", d): np.zeros(n_test) for d in DIMENSIONS}
    for d in DIMENSIONS:
        preds[("B1", d)] = B1[d][te_mask]
        preds[("B2", d)] = hist_dX[d][te_mask]

    cal_band = wes.loc[cal_mask, "horizon_window"].to_numpy()
    for arm in model_arms:
        cols = arms[arm]
        Xf = prepare_matrix(wes.loc[fit_mask], cols, cat_list)
        Xc = prepare_matrix(wes.loc[cal_mask], cols, cat_list)
        Xt = prepare_matrix(wes.loc[te_mask], cols, cat_list)
        for d in DIMENSIONS:
            yf = wes.loc[fit_mask, f"dX_{d}"].to_numpy(dtype=float)
            pred_cal = fit_xgb_seed(Xf, yf, Xc)
            pred_te = fit_xgb_seed(Xf, yf, Xt)
            preds[(arm, d)] = pred_te

            for band in BANDS:
                bm = te_band == band
                resid_cal = np.abs(
                    wes.loc[cal_mask, f"dX_{d}"].to_numpy(dtype=float) - pred_cal)[cal_band == band]
                widths = {lev: conformal_width(resid_cal, alpha)
                          for lev, alpha in NOMINAL.items()}
                key = f"{arm}/{d}/{band}"
                out["results"][key] = {"n_band": int(bm.sum())}
                for view, vm in views.items():
                    s = bm & vm
                    cell = dict(reg_metrics(dX_true[d][s], pred_te[s]))
                    sa = sign_accuracy(dX_true[d][s], pred_te[s], NOISE_FLOOR[d])
                    cell["sign_acc"] = sa["sign_acc"]
                    cell["n_sign"] = sa["n"]
                    # exposure scaling on distance-present rows
                    km = wes.loc[te_mask, "interval_distance_km"].to_numpy(dtype=float)
                    kpd = wes.loc[te_mask, "distance_per_day_km"].to_numpy(dtype=float)
                    dv = s & np.isfinite(dX_true[d]) & np.isfinite(pred_te) & np.isfinite(km)
                    if dv.sum() >= 10:
                        cell["spearman_pred_km"] = round(
                            float(spearmanr(pred_te[dv], km[dv])[0]), 4)
                        cell["spearman_obs_km"] = round(
                            float(spearmanr(dX_true[d][dv], km[dv])[0]), 4)
                        kv = dv & np.isfinite(kpd)
                        if kv.sum() >= 10:
                            cell["spearman_pred_km_day"] = round(
                                float(spearmanr(pred_te[kv], kpd[kv])[0]), 4)
                            cell["spearman_obs_km_day"] = round(
                                float(spearmanr(dX_true[d][kv], kpd[kv])[0]), 4)
                    for lev, w in widths.items():
                        cell[lev] = coverage_view(dX_true[d][s], pred_te[s], w)
                    out["results"][key][view] = cell

    # baselines recorded through the same metric path
    for d in DIMENSIONS:
        for model in ["B0", "B1", "B2"]:
            for band in BANDS:
                bm = te_band == band
                key = f"{model}/{d}/{band}"
                out["results"][key] = {"n_band": int(bm.sum())}
                for view, vm in views.items():
                    s = bm & vm
                    cell = dict(reg_metrics(dX_true[d][s], preds[(model, d)][s]))
                    sa = sign_accuracy(dX_true[d][s], preds[(model, d)][s], NOISE_FLOOR[d])
                    cell["sign_acc"] = sa["sign_acc"]
                    cell["n_sign"] = sa["n"]
                    out["results"][key][view] = cell

    # horizon-scaling table: mean |pred| vs mean |obs| per band (full_test)
    out["horizon_scaling"] = {}
    for d in DIMENSIONS:
        out["horizon_scaling"][d] = {"observed": {}, "B0": {}, "M4_operational": {}}
        for band in BANDS:
            bm = te_band == band
            v = dX_true[d][bm]
            vv = v[np.isfinite(v)]
            out["horizon_scaling"][d]["observed"][band] = (
                round(float(np.mean(np.abs(vv))), 4) if vv.size else None)
            out["horizon_scaling"][d]["B0"][band] = 0.0
            p = preds[("M4_operational", d)][bm]
            pv = p[np.isfinite(p)]
            out["horizon_scaling"][d]["M4_operational"][band] = (
                round(float(np.mean(np.abs(pv))), 4) if pv.size else None)

    # dt distribution per band on test rows
    out["dt_by_band"] = {}
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
    (OUTPUT / "change_space_dynamics_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
