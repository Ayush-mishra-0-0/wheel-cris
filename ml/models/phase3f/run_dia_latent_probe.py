"""Phase 3F diagnostic: multivariate latent/mixed-effects DIAMETER probe.

Falsification experiment (not a production model). Question: can cross-
dimensional geometry recover a predictive signal for wsmDia in change space?

Design (all point-in-time, frozen v3f chronological split):
  - Target: dX_wsmDia = target - base (mm) at 30/60/90d bands (also reported
    in future-state space target_wsmDia = base + dX).
  - Diameter treated as a NOISY observation: we never use its own future or
    rely on clean Delta-D; we pair it with root/flange geometry at t.
  - Arms (fixed XGBoost HP, identical to M4 codebase):
      A1 dia-only
      A2 dia + root
      A3 dia + flange
      A4 dia + root + flange
      A5 + lifecycle/turning/distance context
      A6 + wheel-level random-slope proxy (point-in-time hist_rate)
  - Baselines: B0 zero-change, B1 population drift, B2 historical-rate.
  - M4 reference: reuse the existing Phase 3E M4 feature set on the same split.
  - Holdout stress: never-seen wheelsets (20% by seed), A4/A5/B0/B2.
Metrics per band: MAE / RMSE / R2 / Spearman / sign_acc / var_fidelity /
mean_abs_pred / mean_abs_obs (state-space and Delta-D space).
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
    CATEGORICAL_COLUMNS, add_targets_and_bases, add_historical_rate_predictions,
)
from run_info_ladder import arm_columns, prepare_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"
SEED = 42
BANDS = ["30d", "60d", "90d"]
DIA = "wsmDia"
FLOOR = 1.0  # mm |dX| floor for sign accuracy (matches M4 dia noise floor)

STATE = ["base_wsmDia", "base_wsmRoot", "base_wsmFlangeThickness"]
CONTEXT = ["days_since_turning", "days_since_segment_start", "wheel_age_days_proxy",
           "turning_record_at_measurement", "lifecycle_segment_id",
           "distance_available", "interval_distance_km", "distance_per_day_km"]

ARMS = {
    "A1_dia_only": STATE[:1],
    "A2_dia_plus_root": STATE[:2],
    "A3_dia_plus_flange": [STATE[0], STATE[2]],
    "A4_dia_root_flange": STATE,
    "A5_plus_lifecycle": STATE + CONTEXT,
    "A6_plus_wheel_slope": STATE + CONTEXT + [f"hist_rate_{DIA}"],
}


def reg_metrics(yt, yp):
    yt = np.asarray(yt, dtype=float); yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n < 10:
        return {"n": n, "mae": np.nan, "rmse": np.nan, "r2": np.nan, "spearman": np.nan,
                "sign_acc": np.nan, "var_fidelity": np.nan,
                "mean_abs_pred": np.nan, "mean_abs_obs": np.nan}
    yt, yp = yt[v], yp[v]
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    ssr = float(np.sum((yt - yp) ** 2)); sst = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1 - ssr / sst if sst > 0 else np.nan
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    big = np.abs(yt) > FLOOR
    sign_acc = float(np.mean(np.sign(yt[big]) == np.sign(yp[big]))) if big.sum() >= 10 else np.nan
    return {"n": n, "mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4),
            "spearman": round(rho, 4),
            "sign_acc": round(sign_acc, 4) if sign_acc is not None else None,
            "var_fidelity": round(float(np.std(yp) / np.std(yt)), 4) if np.std(yt) > 0 else np.nan,
            "mean_abs_pred": round(float(np.mean(np.abs(yp))), 4),
            "mean_abs_obs": round(float(np.mean(np.abs(yt))), 4)}


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


def matrix(wes, cols):
    return wes[cols].replace({pd.NA: np.nan}).astype(float).to_numpy()


def population_drift(wes, tr_mask):
    rate = {}
    for band in BANDS:
        sel = tr_mask & (wes["horizon_window"] == band) & np.isfinite(wes[f"dX_{DIA}"])
        rate[band] = float((wes.loc[sel, f"dX_{DIA}"] / wes.loc[sel, "interval_days"]).mean())
    out = np.zeros(len(wes))
    for band in BANDS:
        m = wes["horizon_window"] == band
        out[m] = rate[band] * wes.loc[m, "interval_days"].fillna(0.0)
    return out


def main() -> None:
    wes = pd.read_parquet(V3F)
    wes = add_targets_and_bases(wes)
    wes = add_historical_rate_predictions(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    tr_mask = (wes["split"] == "train").to_numpy()
    te_mask = (wes["split"] == "test").to_numpy()
    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * 0.90)
    fit_mask = np.zeros(len(wes), dtype=bool); fit_mask[tr_pos[:cal_from]] = True
    nm = {"n_train": int(tr_mask.sum()), "n_test": int(te_mask.sum()),
          "n_fit": int(fit_mask.sum())}

    te_band = wes.loc[te_mask, "horizon_window"].to_numpy()
    dX_true = wes.loc[te_mask, f"dX_{DIA}"].to_numpy(dtype=float)
    state_true = wes.loc[te_mask, f"target_{DIA}"].to_numpy(dtype=float)
    base = wes.loc[te_mask, f"base_{DIA}"].to_numpy(dtype=float)

    # ---------- split matrices ----------
    Xf = {}; Xt = {}
    for arm, cols in ARMS.items():
        Xf[arm] = matrix(wes.loc[fit_mask], cols)
        Xt[arm] = matrix(wes.loc[te_mask], cols)

    # M4 reference from the phase3e feature set
    m4cols = arm_columns()["M4_operational"]
    Xf["M4_ref"] = prepare_matrix(wes.loc[fit_mask], m4cols, CATEGORICAL_COLUMNS)
    Xt["M4_ref"] = prepare_matrix(wes.loc[te_mask], m4cols, CATEGORICAL_COLUMNS)

    # ---------- predictions ----------
    preds_dx = {}
    yf_base = wes.loc[fit_mask, f"dX_{DIA}"].to_numpy(dtype=float)
    for arm, X_tr in Xf.items():
        preds_dx[arm] = fit_xgb_seed(X_tr, yf_base, Xt[arm])
    preds_dx["B0"] = np.zeros(nm["n_test"])
    preds_dx["B1"] = population_drift(wes, tr_mask)[te_mask]
    preds_dx["B2"] = (wes.loc[te_mask, f"pred_{DIA}"] - wes.loc[te_mask, f"base_{DIA}"]).to_numpy(dtype=float)

    # ---------- scoring ----------
    out = {"task": "multivariate latent/mixed-effects wsmDia probe (diagnostic)",
           "diameter_treated_as": "noisy observation; joint geometry (root/flange) at t",
           "point_in_time": "all features at base t; wheel slope = only prior pairs",
           "n": nm, "bands": BANDS, "seed": SEED,
           "success_criterion": "A4+/A6 beat B0 zero-change on dX at 30/60/90d",
           "results_dx": {}, "results_state": {}}

    for band in BANDS:
        bm = te_band == band
        out["results_dx"][band] = {arm: reg_metrics(dX_true[bm], p[bm])
                                   for arm, p in preds_dx.items()}
        # state space: pred_state = base + pred_dx
        out["results_state"][band] = {
            arm: reg_metrics(state_true[bm], base[bm] + p[bm])
            for arm, p in preds_dx.items()}

    # ---------- incremental gain table ----------
    gain = {}
    for band in BANDS:
        bm = te_band == band
        mae = {arm: reg_metrics(dX_true[bm], p[bm])["mae"] for arm, p in preds_dx.items()}
        gain[band] = mae
    out["incremental_mae_dx"] = gain

    # ---------- loco/wheelset holdout stress (never-seen wheelsets) ----------
    rng = np.random.RandomState(SEED)
    wids = wes["wheelset_equipment_id"].unique()
    ho_w = set(rng.choice(np.sort(wids), size=int(0.2 * len(wids)), replace=False))
    ho_mask = wes["wheelset_equipment_id"].isin(ho_w).to_numpy()
    ho_band = wes.loc[ho_mask, "horizon_window"].to_numpy()
    ho_te = pd.concat([
        wes.loc[ho_mask].sort_values("measurement_timestamp"),
    ])
    ho_tr = wes.loc[~ho_mask].sort_values("measurement_timestamp")
    Xth = {a: matrix(ho_te, ARMS[a]) for a in ["A4_dia_root_flange", "A5_plus_lifecycle"]}
    Xth["B2"] = np.zeros(len(ho_te))
    yfh = ho_tr[f"dX_{DIA}"].to_numpy(dtype=float)
    Xfh = {a: matrix(ho_tr, ARMS[a]) for a in ARMS}
    Xfh["lambda_A4"] = matrix(ho_tr, ARMS["A4_dia_root_flange"])
    Xfh["lambda_A5"] = matrix(ho_tr, ARMS["A5_plus_lifecycle"])
    ho_dx = ho_te[f"dX_{DIA}"].to_numpy(dtype=float)
    ho_base = ho_te[f"base_{DIA}"].to_numpy(dtype=float)
    ho_state = ho_te[f"target_{DIA}"].to_numpy(dtype=float)
    ho_pred = {}
    ho_pred["A4"] = fit_xgb_seed(Xfh["lambda_A4"], yfh, Xth["A4_dia_root_flange"])
    ho_pred["A5"] = fit_xgb_seed(Xfh["lambda_A5"], yfh, Xth["A5_plus_lifecycle"])
    ho_pred["B0"] = np.zeros(len(ho_dx))
    ho_pred["B2"] = (ho_te[f"pred_{DIA}"] - ho_te[f"base_{DIA}"]).to_numpy(dtype=float)
    out["holdout_wheelsets"] = {"n_wheels_heldout": len(ho_w), "n_rows": int(ho_mask.sum())}
    out["holdout_dx"] = {}
    out["holdout_state"] = {}
    for band in BANDS:
        bm = ho_band == band
        out["holdout_dx"][band] = {a: reg_metrics(ho_dx[bm], p[bm])
                                   for a, p in ho_pred.items()}
        out["holdout_state"][band] = {a: reg_metrics(ho_state[bm], ho_base[bm] + p[bm])
                                      for a, p in ho_pred.items()}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dia_latent_multivariate_probe.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")

    # print compact table
    print("=== dX_wsmDia MAE / Spearman / sign_acc by band ===")
    for band in BANDS:
        r = out["results_dx"][band]
        line = " | ".join(f"{a}: {r[a]['mae']:.3f}/{r[a]['spearman']:.2f}/"
                          f"{r[a]['sign_acc'] if r[a]['sign_acc'] is not None else float('nan') and 0:.2f}"
                          for a in ["B0", "B1", "B2", "A1_dia_only", "A2_dia_plus_root",
                                    "A3_dia_plus_flange", "A4_dia_root_flange",
                                    "A5_plus_lifecycle", "A6_plus_wheel_slope", "M4_ref"])
        print(f"  {band}: {line}")
    print("\n=== state-space wsmDia MAE by band ===")
    for band in BANDS:
        r = out["results_state"][band]
        line = " | ".join(f"{a}: {r[a]['mae']:.3f}" for a in
                          ["B0", "B2", "A1_dia_only", "A4_dia_root_flange", "M4_ref"])
        print(f"  {band}: {line}")
    print("\n=== holdout (never-seen wheelsets) dX MAE ===")
    for band in BANDS:
        r = out["holdout_dx"][band]
        line = " | ".join(f"{a}: {r[a]['mae']:.3f}" for a in ["B0", "B2", "A4", "A5"])
        print(f"  {band}: {line}")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()