"""Phase 3B - Engineering State Evolution (next-state regression).

Predicts the NEXT measured engineering state (absolute value per dimension)
from current state + exposure. This is "next wheel health": given today's
inspection, what will the next inspection find.

Chronological / forward-looking evaluation (train early, predict later).

Metrics per dimension: RMSE(mm), MAE(mm), Spearman (rank correlation), R2, and
the persistence baseline (predicting current state unchanged) to show the
value-add of exposure + history.

Boundary-crossing pairs (turning/replacement resets) are excluded from training
so the model learns within-life evolution only.
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
TARGET_DIMS = DIMENSIONS


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
        return {"rmse": np.nan, "mae": np.nan, "spearman": np.nan, "r2": np.nan, "n": int(valid.sum())}
    yt, yp = y_true[valid], y_pred[valid]
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mae = float(np.mean(np.abs(yt - yp)))
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"rmse": round(rmse, 4), "mae": round(mae, 4), "spearman": round(rho, 4),
            "r2": round(r2, 4), "n": int(valid.sum())}


def _persistence_metrics(y_true, y_base):
    valid = np.isfinite(y_true) & np.isfinite(y_base)
    yt, yb = y_true[valid], y_base[valid]
    return {"persistence_mae": round(float(np.mean(np.abs(yt - yb))), 4),
            "persistence_rmse": round(float(np.sqrt(np.mean((yt - yb) ** 2))), 4),
            "n": int(valid.sum())}


def main() -> None:
    pairs = pd.read_parquet(DATA_DIR / "degradation_pairs.parquet")
    wear = pairs.loc[~pairs["crosses_reset"]].copy()
    wear = wear.dropna(subset=["next_record_id"]).copy()

    for d in DIMENSIONS:
        t1, t2 = f"{d}1", f"{d}2"
        v1 = wear[f"{t1}_quality"].eq("OBSERVED_VALID")
        v2 = wear[f"{t2}_quality"].eq("OBSERVED_VALID")
        wear[f"target_{d}"] = np.where(
            v1 & v2, (wear[f"next_{t1}"] + wear[f"next_{t2}"]) / 2.0,
            np.where(v1, wear[f"next_{t1}"], np.where(v2, wear[f"next_{t2}"], np.nan)))
        wear[f"base_{d}"] = np.where(
            v1 & v2, (wear[t1] + wear[t2]) / 2.0,
            np.where(v1, wear[t1], np.where(v2, wear[t2], np.nan)))

    Y = wear[[f"target_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)
    B = wear[[f"base_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)

    wear = wear.sort_values("measurement_timestamp")
    order = np.arange(len(wear))
    tr_idx = order < 0.8 * len(wear)
    te_idx = order >= 0.8 * len(wear)

    Xtr_enc, encoders = _label_encode_cats(wear.loc[tr_idx, FEATURE_COLUMNS])
    Xte_enc, _ = _label_encode_cats(wear.loc[te_idx, FEATURE_COLUMNS], encoders)
    for c in QUALITY_COLUMNS:
        for enc, src in ((Xtr_enc, Xtr_enc), (Xte_enc, Xte_enc)):
            enc[c + "_code"] = src[c].fillna("MISSING").map(
                {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
                 "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    num_cols = STATE_COLUMNS + EXPOSURE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]

    Xtr = Xtr_enc[num_cols].astype(float).fillna(0.0)
    Xte = Xte_enc[num_cols].astype(float).fillna(0.0)
    ytr, yte = Y[tr_idx], Y[te_idx]
    bte = B[te_idx]

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
        mte_ridge = _reg_metrics(yte[:, di], ridge_pred_te[:, di])
        mte_rf = _reg_metrics(yte[:, di], rf.predict(Xte)[:, di])
        mte_persist = _persistence_metrics(yte[:, di], bte[:, di])
        results[d] = {"test_ridge": mte_ridge, "test_randomforest": mte_rf,
                      "persistence_baseline": mte_persist, "target_unit": "mm"}
        print(f"{d:18s} Ridge MAE={mte_ridge['mae']:.4f} RMSE={mte_ridge['rmse']:.4f} "
              f"R2={mte_ridge['r2']:.3f} rho={mte_ridge['spearman']:.3f} | "
              f"persistence MAE={mte_persist['persistence_mae']:.4f}")

    out = {
        "input": str((DATA_DIR / "degradation_pairs.parquet").relative_to(ROOT)),
        "n_train_pairs": int(np.sum(tr_idx)),
        "n_test_pairs": int(np.sum(te_idx)),
        "split": "chronological 80/20",
        "task": "predict NEXT measured engineering state (absolute, mm)",
        "note": "Next-state regression; persistence (current state) is baseline. "
                "Exposure is duration-based (days), not km (RTIS km blocked). "
                "Reset-crossing pairs excluded.",
        "per_dimension": results,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "degradation_results.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Phase 3B - Engineering State Evolution (next-state model)",
        "",
        "Predicts the NEXT measured engineering state (absolute mm) from current",
        "state + exposure. Chronological 80/20 (forward-looking). The **persistence**",
        "baseline (predict current state unchanged) shows the value-add of exposure",
        "+ history. Reset-crossing pairs excluded (within-life evolution only).",
        "",
        "| Dimension | Test n | Ridge MAE (mm) | Ridge RMSE (mm) | Ridge R2 | Persist MAE (mm) | Persist RMSE (mm) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for d in TARGET_DIMS:
        r = results[d]
        lines.append(f"| {d} | {r['test_ridge']['n']:,} | {r['test_ridge']['mae']:.4f} "
                     f"| {r['test_ridge']['rmse']:.4f} | {r['test_ridge']['r2']:.3f} "
                     f"| {r['persistence_baseline']['persistence_mae']:.4f} "
                     f"| {r['persistence_baseline']['persistence_rmse']:.4f} |")
    lines += [
        "",
        "## Reading this",
        "",
        "- MAE in mm = error in the NEXT measured value prediction (best accuracy of",
        "  the estimated next wheel state).",
        "- Persistence (predict current state unchanged) is the naive baseline; the",
        "  model should match or beat it while also estimating *direction*.",
        "- R2 / Spearman indicate whether predicted next state tracks the actual next",
        "  measurement (supports prioritization).",
        "- Exposure is duration-based (days), not km: RTIS km semantics blocked.",
    ]
    (OUTPUT / "degradation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
