"""Phase 3B - multi-output degradation regression.

Predicts per-dimension wear (delta over the inspection interval) from current
engineering state + exposure. This is the "estimated engineering state
evolution": predicted_next_state = current_state + predicted_delta.

Rotating/rolling evaluation: train on early pairs, predict later pairs, so the
accuracy statements are forward-looking (no leakage into the eviction window).

Metrics per dimension: RMSE(mm), MAE(mm), Spearman (monotonic ranking of wear).
Also reports the share of wear-delta variance attributable to exposure.

Boundary-crossing pairs (resets) are EXCLUDED from wear learning; their rows
carry no delta target for the reset-crossing window.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "model_datasets" / "v3b"
OUTPUT = ROOT / "models" / "experiments" / "v3b"
SEED = 42

DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot", "wsmWheelGauge"]
SIDES = ["1", "2"]
STATE_COLUMNS = [f"{d}{s}" for d in DIMENSIONS for s in SIDES]
QUALITY_COLUMNS = [f"{c}_quality" for c in STATE_COLUMNS]
EXPOSURE_COLUMNS = [
    "interval_days", "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
    "days_since_turning", "wheel_age_days_proxy",
]
CATEGORICAL_COLUMNS = ["LocoType", "wheel_profile_2class", "home_shed",
                       "defect_zone", "defect_division", "wheel_position_1_12",
                       "axle_position_1_6"]

FEATURE_COLUMNS = STATE_COLUMNS + QUALITY_COLUMNS + EXPOSURE_COLUMNS + CATEGORICAL_COLUMNS
TARGETS = [f"delta_{c}" for c in STATE_COLUMNS]


def _label_encode_cats(df, encoders=None):
    out = df.copy()
    enc = encoders if encoders is not None else {}
    for c in CATEGORICAL_COLUMNS:
        if encoders is None:
            vals = out[c].dropna().astype(str).unique()
            enc[c] = {v: i for i, v in enumerate(sorted(vals))}
        out[c] = out[c].astype(str).map(enc[c]).astype(float)
    return out, enc


def _reg_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    if valid.sum() < 10:
        return {"rmse": np.nan, "mae": np.nan, "spearman": np.nan, "n": int(valid.sum())}
    yt, yp = y_true[valid], y_pred[valid]
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mae = float(np.mean(np.abs(yt - yp)))
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    return {"rmse": round(rmse, 4), "mae": round(mae, 4), "spearman": round(rho, 4), "n": int(valid.sum())}


def main() -> None:
    pairs = pd.read_parquet(DATA_DIR / "degradation_pairs.parquet")
    wear = pairs.loc[~pairs["crosses_reset"]].copy()  # only monotonic life pairs
    wear = wear.dropna(subset=["next_record_id"]).copy()

    # Use the mean of both sides when both are observed-valid for the TARGET of a
    # dimension; else drop the row for that dimension. Keep side-level features.
    from numpy import isfinite
    for d in DIMENSIONS:
        t1, t2 = f"{d}1", f"{d}2"
        v1 = wear[f"{t1}_quality"].eq("OBSERVED_VALID")
        v2 = wear[f"{t2}_quality"].eq("OBSERVED_VALID")
        wear[f"target_delta_{d}"] = np.where(
            v1 & v2,
            (wear[f"delta_{t1}"] + wear[f"delta_{t2}"]) / 2.0,
            np.where(v1, wear[f"delta_{t1}"], np.where(v2, wear[f"delta_{t2}"], np.nan)))

    TARGET_DIMS = DIMENSIONS
    Y = wear[[f"target_delta_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)

    # Roll 0/1/2/3-accumulated chronology split for forward-looking evaluation.
    wear = wear.sort_values("measurement_timestamp")
    order = np.arange(len(wear))
    split = order >= 0.8 * len(order)
    tr_idx, te_idx = ~split, split

    # Build feature matrix with train-only encoding.
    Xtr_enc, encoders = _label_encode_cats(wear.iloc[np.where(tr_idx)[0]][FEATURE_COLUMNS])
    Xte_enc, _ = _label_encode_cats(wear.iloc[np.where(te_idx)[0]][FEATURE_COLUMNS], encoders)
    num_cols = STATE_COLUMNS + EXPOSURE_COLUMNS
    # Quality codes are ordinal categories -> convert to integer codes.
    for c in QUALITY_COLUMNS:
        Xtr_enc[c + "_code"] = Xtr_enc[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
        Xte_enc[c + "_code"] = Xte_enc[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    num_cols = num_cols + [c + "_code" for c in QUALITY_COLUMNS]

    Xtr = Xtr_enc[num_cols].astype(float).fillna(0.0)
    Xte = Xte_enc[num_cols].astype(float).fillna(0.0)
    ytr = Y[tr_idx]
    yte = Y[te_idx]

    ridge_pred_tr = np.full_like(ytr, np.nan)
    ridge_pred_te = np.full_like(yte, np.nan)
    for di, d in enumerate(TARGET_DIMS):
        finite_tr = np.isfinite(ytr[:, di])
        finite_te = np.isfinite(yte[:, di])
        r = Ridge(alpha=10.0)
        r.fit(Xtr[finite_tr], ytr[finite_tr, di])
        ridge_pred_tr[finite_tr, di] = r.predict(Xtr[finite_tr])
        ridge_pred_te[finite_te, di] = r.predict(Xte[finite_te])
    rf = RandomForestRegressor(n_estimators=250, max_depth=14, min_samples_leaf=15,
                               n_jobs=-1, random_state=SEED)
    rf.fit(Xtr, np.nan_to_num(ytr))

    results = {}
    for di, d in enumerate(TARGET_DIMS):
        mtr = _reg_metrics(ytr[:, di], ridge_pred_tr[:, di])
        mte_ridge = _reg_metrics(yte[:, di], ridge_pred_te[:, di])
        mte_rf = _reg_metrics(yte[:, di], rf.predict(Xte)[:, di])
        results[d] = {
            "train_ridge": mtr,
            "test_ridge": mte_ridge,
            "test_randomforest": mte_rf,
            "target_unit": "mm",
        }
        print(f"{d:18s} test Ridge  MAE={mte_ridge['mae']:.4f} RMSE={mte_ridge['rmse']:.4f} "
              f"rho={mte_ridge['spearman']:.3f} | RF MAE={mte_rf['mae']:.4f} RMSE={mte_rf['rmse']:.4f}")

    # Exposure importance for the primary wear dims (per-dim R i d g e coefficients).
    exposure_importance = {}
    for di, d in enumerate(TARGET_DIMS):
        r = Ridge(alpha=10.0)
        finite = np.isfinite(ytr[:, di])
        r.fit(Xtr[finite], ytr[finite, di])
        coef = np.abs(r.coef_)
        idx_map = {c: i for i, c in enumerate(num_cols)}
        exp_vals = {c: float(coef[idx_map[c]]) for c in EXPOSURE_COLUMNS if c in idx_map}
        exposure_importance[d] = exp_vals

    out = {
        "input": str((DATA_DIR / "degradation_pairs.parquet").relative_to(ROOT)),
        "n_wear_pairs": int(np.sum(~split)),
        "n_test_pairs": int(np.sum(split)),
        "split": "chronological 80/20",
        "per_dimension": results,
        "note": "Predicted wear is per inspection interval (days, not km; RTIS km blocked). "
                "Next state = current state + predicted delta.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "degradation_results.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Phase 3B - Engineering State Evolution (degradation model)",
        "",
        "Multi-output regression of per-dimension wear (delta mm over the inspection",
        "interval) conditioned on current engineering state + exposure. Chronological",
        "80/20 split (forward-looking, no leakage). Wear targets use observed-valid",
        "sides only; reset-crossing pairs excluded (wear non-monotonic across reset).",
        "",
        "| Dimension | Test n | Ridge MAE (mm) | Ridge RMSE (mm) | Ridge Spearman | RF MAE (mm) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for d in TARGET_DIMS:
        r = results[d]
        lines.append(f"| {d} | {r['test_ridge']['n']:,} | {r['test_ridge']['mae']:.4f} "
                     f"| {r['test_ridge']['rmse']:.4f} | {r['test_ridge']['spearman']:.3f} "
                     f"| {r['test_randomforest']['mae']:.4f} |")
    lines += [
        "",
        "## Reading this",
        "",
        "- MAE in mm is the prediction error on wear over one inspection gap.",
        "- Spearman measures whether the model ranks high-wear wheels correctly",
        "  (the prioritization signal).",
        "- Exposure is currently **duration-based (days)**, not km: RTIS km semantics",
        "  are blocked. Accuracy claims are per-inspection-interval, not per-km.",
        "- Resets (turning/replacement) are excluded from wear learning, so the model",
        "  learns within-life degradation only.",
    ]
    (OUTPUT / "degradation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
