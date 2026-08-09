"""Phase 3C Stage B - Diagnostic replacement-exclusion ablation (memo only).

Question: how much of the 17.95 mm diameter MAE in the v3b next-state model is
lifecycle (replacement) contamination?

Method (per phase3c_plan.md section 6):
  - Fixed cohort: the same frozen rows of degradation_pairs.parquet used by the
    existing v3b model; identical test set for both arms.
  - Experiment A (baseline): old v3b training rows (current crosses_reset =
    turning-only exclusion).
  - Experiment B: same rows minus replacement-boundary pairs from the Stage A
    engineering event ledger (a pair whose current->next interval contains a
    ledger replacement event, strictly between current and next measurement).
  - Identical features, chronological 80/20 split, seeds, hyperparameters; ONLY
    the training-row exclusion differs.
  - Both arms evaluated on the SAME test indices.

REPLICATION FINDING: the stored 17.95 mm baseline (degradation_results.json) is
produced by a feature/target MISALIGNMENT: the original script computes Y/B on
the parquet (wheelset-grouped) row order but indexes them with positions derived
AFTER sorting by timestamp (run_degradation_model.py lines 101-122), while X is
indexed after the same sort. The stored number is therefore not a clean
estimation error. To be faithful to the documented baseline we run BOTH:
  - faithful replication of the original pipeline (Experiment A reproduces
    17.9511 exactly), and
  - a correctly-aligned variant (Y/B computed in the same sorted order as X) to
    measure the true contamination effect on a sound pipeline.

Output is a memo only (not a benchmark, not a Phase 3C result).
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
LEDGER = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0" / "engineering_event_ledger.parquet"
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


def _prepare_targets(wear):
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
    return wear


def _fit_predict(wear, exclude_tr, aligned=False):
    """Chronological 80/20 next-state model (Ridge + RF), matching
    run_degradation_model.py hyperparameters/seed/split.

    aligned=True  : Y/B computed in the same sorted-by-timestamp order as X
                    (correct).
    aligned=False : faithful replication of the stored baseline, where Y/B are
                    computed on the pre-sort parquet row order and indexed with
                    post-sort positions (the misalignment in the existing
                    pipeline). exclude_tr must be aligned to the sorted order in
                    both cases.
    """
    Y_pre = wear[[f"target_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)
    B_pre = wear[[f"base_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)

    wear = wear.sort_values("measurement_timestamp")
    order = np.arange(len(wear))
    tr_idx = order < 0.8 * len(wear)
    te_idx = order >= 0.8 * len(wear)
    if exclude_tr is not None:
        ex = exclude_tr.to_numpy(dtype=bool) if hasattr(exclude_tr, "to_numpy") else np.asarray(exclude_tr, dtype=bool)
        tr_idx = tr_idx & ~ex

    if aligned:
        Y = wear[[f"target_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)
        B = wear[[f"base_{d}" for d in TARGET_DIMS]].to_numpy(dtype=float)
    else:
        Y, B = Y_pre, B_pre

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

    ridge_pred_te = np.full_like(yte, np.nan)
    for di, d in enumerate(TARGET_DIMS):
        finite_tr = np.isfinite(ytr[:, di])
        finite_te = np.isfinite(yte[:, di])
        r = Ridge(alpha=10.0)
        r.fit(Xtr[finite_tr], ytr[finite_tr, di])
        ridge_pred_te[finite_te, di] = r.predict(Xte[finite_te])
    rf = RandomForestRegressor(n_estimators=250, max_depth=14, min_samples_leaf=15,
                               n_jobs=-1, random_state=SEED)
    rf.fit(Xtr, np.nan_to_num(ytr))

    results = {}
    for di, d in enumerate(TARGET_DIMS):
        results[d] = {
            "test_ridge": _reg_metrics(yte[:, di], ridge_pred_te[:, di]),
            "test_randomforest": _reg_metrics(yte[:, di], rf.predict(Xte)[:, di]),
            "persistence_baseline": _persistence_metrics(yte[:, di], bte[:, di]),
        }
    return results


def _ledger_replacement_pairs(pairs):
    """Boolean mask (aligned to the input row order): pairs whose (current, next]
    interval contains a ledger replacement event for the same wheelset, strictly
    between current and next measurement (lo < evt <= hi)."""
    led = pd.read_parquet(LEDGER)
    rep = led[led["event_type"] == "replacement"][["wheelset_equipment_id", "event_date"]].dropna()
    rep["wid"] = rep["wheelset_equipment_id"].astype("int64")
    ev = pd.to_datetime(rep["event_date"]).to_numpy(dtype="datetime64[us]")
    rwids = rep["wid"].to_numpy()
    by = {k: np.sort(ev[rwids == k]) for k in np.unique(rwids)}

    lo = pd.to_datetime(pairs["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    hi = pd.to_datetime(pairs["next_time"]).to_numpy(dtype="datetime64[us]")
    pw = pairs["wheelset_equipment_id"].astype("int64").to_numpy()
    mask = np.zeros(len(pairs), dtype=bool)
    for i in range(len(pairs)):
        dts = by.get(pw[i])
        if dts is None or len(dts) == 0:
            continue
        i0 = np.searchsorted(dts, lo[i], side="right")
        if i0 < len(dts) and dts[i0] <= hi[i]:
            mask[i] = True
    return mask


def _summarize_pair(a, b, name):
    per_dim = {}
    for d in TARGET_DIMS:
        mae_attrib = a[d]["test_ridge"]["mae"] - b[d]["test_ridge"]["mae"]
        frac = mae_attrib / a[d]["test_ridge"]["mae"] if a[d]["test_ridge"]["mae"] else np.nan
        per_dim[d] = {
            "unit": "mm",
            "exp_a_ridge_mae": a[d]["test_ridge"]["mae"],
            "exp_b_ridge_mae": b[d]["test_ridge"]["mae"],
            "mae_change": round(mae_attrib, 4),
            "mae_attributable_fraction": round(float(frac), 4),
            "exp_a_ridge_rmse": a[d]["test_ridge"]["rmse"],
            "exp_b_ridge_rmse": b[d]["test_ridge"]["rmse"],
            "exp_a_ridge_r2": a[d]["test_ridge"]["r2"],
            "exp_b_ridge_r2": b[d]["test_ridge"]["r2"],
            "exp_a_rf_mae": a[d]["test_randomforest"]["mae"],
            "exp_b_rf_mae": b[d]["test_randomforest"]["mae"],
            "persistence_mae": a[d]["persistence_baseline"]["persistence_mae"],
        }
        print(f"[{name}] {d:20s} A MAE={per_dim[d]['exp_a_ridge_mae']:.4f} "
              f"B MAE={per_dim[d]['exp_b_ridge_mae']:.4f} "
              f"attrib={per_dim[d]['mae_attributable_fraction']:.3f} "
              f"| RF A={per_dim[d]['exp_a_rf_mae']:.4f} B={per_dim[d]['exp_b_rf_mae']:.4f}")
    return per_dim


def main() -> None:
    pairs = pd.read_parquet(DATA_DIR / "degradation_pairs.parquet")
    wear = pairs.loc[~pairs["crosses_reset"]].copy()
    wear = wear.dropna(subset=["next_record_id"]).copy()
    wear = _prepare_targets(wear)

    wear_sorted = wear.sort_values("measurement_timestamp")
    repl_mask = _ledger_replacement_pairs(wear_sorted)
    tr_pos = np.arange(len(wear_sorted)) < 0.8 * len(wear_sorted)
    te_pos = np.arange(len(wear_sorted)) >= 0.8 * len(wear_sorted)
    repl_tr = int(np.sum(repl_mask & tr_pos))
    repl_te = int(np.sum(repl_mask & te_pos))
    n_train_a = int(np.sum(tr_pos))
    n_train_b = int(np.sum(tr_pos & ~repl_mask))
    n_test = int(np.sum(te_pos))

    # Pair 1: faithful replication of the existing v3b pipeline (A must equal the
    # stored 17.9511 baseline).
    fa = _fit_predict(wear, exclude_tr=None, aligned=False)
    fb = _fit_predict(wear, exclude_tr=repl_mask, aligned=False)
    faithful = _summarize_pair(fa, fb, "faithful")

    # Pair 2: correctly aligned pipeline (sound estimation, true contamination).
    ca = _fit_predict(wear, exclude_tr=None, aligned=True)
    cb = _fit_predict(wear, exclude_tr=repl_mask, aligned=True)
    aligned = _summarize_pair(ca, cb, "aligned ")

    out = {
        "input_pairs": str((DATA_DIR / "degradation_pairs.parquet").relative_to(ROOT)),
        "input_ledger": str(LEDGER.relative_to(ROOT)),
        "split": "chronological 80/20, frozen row indices, identical test set both arms",
        "task": "diagnostic ablation, memo only (not a benchmark, not a Phase 3C result)",
        "experiment_a": "old v3b training rows (turning-only crosses_reset exclusion)",
        "experiment_b": "same rows minus replacement-boundary pairs (Stage A ledger)",
        "n_train_a": n_train_a,
        "n_train_b": n_train_b,
        "n_replacement_pairs_excluded_from_train": repl_tr,
        "n_test": n_test,
        "replacement_pairs_in_test": repl_te,
        "replication_note": (
            "stored 17.95 mm baseline is produced by a feature/target misalignment "
            "in run_degradation_model.py (Y/B computed pre-sort, indexed post-sort); "
            "faithful arm reproduces it exactly, aligned arm gives sound numbers"),
        "faithful_replication": faithful,
        "correctly_aligned": aligned,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "replacement_contamination_results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
