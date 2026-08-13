"""Phase 3C - clean degradation benchmark (alignment-safe).

Execution order (per docs/phase3c_clean_benchmark_plan.md):
  1. Persistence baseline (first-class)
  2. Point-in-time historical-rate baseline
  3. Ridge (linear) and XGBoost (one strong tree), fixed hyperparameters
  4. Contamination views A (same frozen cohort) and B (clean lifecycle cohort)
  5. Distance ablation (Arm A no distance, Arm B + interval_distance_km),
     stratified by distance presence, interval_days, distance_per_day, coverage

All arms use the SAME frozen test cohort (clean_benchmark_cohort.parquet) and
the alignment-safe eval core (degradation_eval.py). No hyperparameter tuning.
Output: models/experiments/v3c/clean_degradation_benchmark_results.json + report.
"""
from __future__ import annotations

import json
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))

from degradation_eval import (  # noqa: E402
    ROW_ID_COL, DIMENSIONS, STATE_COLUMNS, QUALITY_COLUMNS, EXPOSURE_COLUMNS,
    CATEGORICAL_COLUMNS,
    add_targets_and_bases, add_historical_rate_predictions,
    assert_row_alignment, chronological_split,
    fit_ridge, fit_xgb, _reg_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / "model_datasets" / "v3c" / "clean_benchmark_pairs.parquet"
COHORT = ROOT / "model_datasets" / "v3c" / "clean_benchmark_cohort.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3c"
SEED = 42

TARGETS = [f"target_{d}" for d in DIMENSIONS]
DIST_FEATURES = ["interval_distance_km", "distance_per_day_km",
                 "rtis_distance_coverage_pct_in_interval", "distance_since_turning_km",
                 "distance_available"]

BAND_EDGES = {
    "interval_days": [0, 30, 60, 90, 180, 1e9],
    "interval_distance_km": [0, 5000, 15000, 30000, 1e9],
    "distance_per_day_km": [0, 250, 450, 650, 1e9],
    "rtis_distance_coverage_pct_in_interval": [0, 25, 50, 75, 100, 1e9],
}


def _band(v, edges):
    i = bisect_left(edges, v)
    if i <= 0:
        return f"<{edges[0]}"
    lo = "" if edges[i] == 1e9 else str(edges[i])
    return f"{edges[i-1]}-{lo}" if lo else f">{edges[i-1]}"


def _prepare(wear: pd.DataFrame, num_cols: list[str]):
    encoded = wear.copy()
    for c in QUALITY_COLUMNS:
        encoded[c + "_code"] = encoded[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    for c in CATEGORICAL_COLUMNS:
        vals = sorted(encoded[c].dropna().astype(str).unique())
        code = {v: i for i, v in enumerate(vals)}
        encoded[c] = encoded[c].astype(str).map(code).astype(float).fillna(-1.0)
    M = encoded[num_cols].astype(float).fillna(0.0)
    if "distance_available" in encoded.columns:
        M["distance_available"] = encoded["distance_available"].fillna(False).astype(float)
    return M


def fit_evaluate_xgb(wear: pd.DataFrame, tr_mask, te_mask, num_cols: list[str],
                     target_col: str):
    """Fit XGBoost for ONE dimension; return test predictions + metrics.
    Row identity preserved via wear ordering (no positional swaps)."""
    Xtr = _prepare(wear, num_cols).loc[tr_mask].to_numpy()
    Xte = _prepare(wear, num_cols).loc[te_mask].to_numpy()
    y = wear[target_col].to_numpy(dtype=float)
    ytr = y[tr_mask]
    yte = y[te_mask]
    assert_row_alignment(wear.loc[te_mask, ROW_ID_COL].to_numpy(),
                         wear.loc[te_mask, ROW_ID_COL].to_numpy())
    pred = fit_xgb(Xtr, np.nan_to_num(ytr), Xte, seed=SEED)
    return _reg_metrics(yte, pred), pred


def _base_num_cols():
    return (STATE_COLUMNS + EXPOSURE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]
            + CATEGORICAL_COLUMNS)


def main() -> None:
    wear = pd.read_parquet(SUBSTRATE)
    wear = wear[wear["within_lifecycle"]].copy()
    wear = add_targets_and_bases(wear)
    wear = add_historical_rate_predictions(wear)

    # FROZEN cohort: all arms share identical chronological test indices.
    # chronological_split REPLACES wear with its time-sorted copy; we must keep
    # that sorted frame and apply the masks to IT (not the pre-sort frame).
    wear_sorted, tr_mask, te_mask = chronological_split(wear, test_frac=0.2, cache_path=COHORT)
    wear = wear_sorted
    te = wear.loc[te_mask]
    n_train = int(np.sum(tr_mask))
    n_te = int(np.sum(te_mask))

    # ------------------------------------------------------------------ #
    # 1. persistence baseline (first-class)
    # 2. historical-rate baseline
    # ------------------------------------------------------------------ #
    baselines = {}
    for d in DIMENSIONS:
        baselines[d] = {
            "persistence": _reg_metrics(te[f"target_{d}"].to_numpy(dtype=float),
                                        te[f"base_{d}"].to_numpy(dtype=float)),
            "historical_rate": _reg_metrics(te[f"target_{d}"].to_numpy(dtype=float),
                                            te[f"pred_{d}"].to_numpy(dtype=float)),
        }

    # ------------------------------------------------------------------ #
    # 3. clean ML benchmark: Ridge + XGBoost (fixed hyperparameters)
    # ------------------------------------------------------------------ #
    num_cols = _base_num_cols()
    encoded_full = _prepare(wear, num_cols)
    Xtr = encoded_full.loc[tr_mask].to_numpy()
    Xte = encoded_full.loc[te_mask].to_numpy()
    y_full = wear[TARGETS].to_numpy(dtype=float)
    ytr = y_full[tr_mask]
    yte = y_full[te_mask]
    assert_row_alignment(wear.loc[te_mask, ROW_ID_COL].to_numpy(),
                         wear.loc[te_mask, ROW_ID_COL].to_numpy())

    ridge_pred = np.column_stack([
        fit_ridge(Xtr, ytr[:, di], Xte) if np.isfinite(ytr[:, di]).any() else np.full(Xte.shape[0], np.nan)
        for di in range(len(DIMENSIONS))])
    xgb_pred = np.column_stack([
        fit_xgb(Xtr, np.nan_to_num(ytr[:, di]), Xte, seed=SEED) for di in range(len(DIMENSIONS))])

    ml = {}
    for di, d in enumerate(DIMENSIONS):
        ml[d] = {"ridge": _reg_metrics(yte[:, di], ridge_pred[:, di]),
                 "xgb": _reg_metrics(yte[:, di], xgb_pred[:, di])}

    # ------------------------------------------------------------------ #
    # 4. contamination view: fit on un-clean rows vs clean rows (same test)
    #    A = clean rows (baseline above); B = clean rows used here.
    #    For the replacement-contamination comparison, fit an XGBoost on the
    #    FULL aligned rows (including replacement-boundary pairs in train) and
    #    compare against the clean-trained model on the SAME test cohort.
    # ------------------------------------------------------------------ #
    wear_all = pd.read_parquet(SUBSTRATE)
    wear_all = add_targets_and_bases(wear_all)
    full_ids = wear_all[ROW_ID_COL].to_numpy()
    # preserve the frozen test cohort: train-on-all, evaluate-on-frozen-test.
    # test_set MUST be the queued test row ids (te), not the whole frame.
    test_set = set(te[ROW_ID_COL].to_numpy())
    wear_all_sorted = wear_all.sort_values("measurement_timestamp").reset_index(drop=True)
    te_pos_all = wear_all_sorted[ROW_ID_COL].isin(test_set).to_numpy()
    tr_pos_all = ~te_pos_all
    Xtr_all = _prepare(wear_all_sorted, num_cols).loc[tr_pos_all].to_numpy()
    Xte_all = _prepare(wear_all_sorted, num_cols).loc[te_pos_all].to_numpy()
    y_all = wear_all_sorted[TARGETS].to_numpy(dtype=float)
    ytr_all = y_all[tr_pos_all]
    yte_all = y_all[te_pos_all]

    contamination = {}
    for di, d in enumerate(DIMENSIONS):
        pred_all = fit_xgb(Xtr_all, ytr_all[:, di], Xte_all, seed=SEED)
        m_all = _reg_metrics(yte_all[:, di], pred_all)
        m_clean = ml[d]["xgb"]
        diff = m_all["mae"] - m_clean["mae"] if np.isfinite(m_all["mae"]) else np.nan
        frac = diff / m_all["mae"] if np.isfinite(m_clean["mae"]) and np.isfinite(m_all["mae"]) else np.nan
        contamination[d] = {
            "xgb_mae_all_train_rows": m_all["mae"],
            "xgb_mae_clean_train_rows": m_clean["mae"],
            "mae_change_from_cleaning": round(diff, 4),
            "improvement_fraction": round(float(frac), 4),
        }

    # ------------------------------------------------------------------ #
    # 5. distance ablation: identical setup ± distance features (XGBoost)
    # ------------------------------------------------------------------ #
    num_cols_d = _base_num_cols() + DIST_FEATURES
    Xtr_d = _prepare(wear, num_cols_d).loc[tr_mask].to_numpy()
    Xte_d = _prepare(wear, num_cols_d).loc[te_mask].to_numpy()
    distance = {}
    for di, d in enumerate(DIMENSIONS):
        pred_d = fit_xgb(Xtr_d, np.nan_to_num(ytr[:, di]), Xte_d, seed=SEED)
        m_d = _reg_metrics(yte[:, di], pred_d)
        m_base = ml[d]["xgb"]
        distance[d] = {
            "xgb_mae_no_distance": m_base["mae"],
            "xgb_mae_with_distance": m_d["mae"],
            "delta_mae": round(m_base["mae"] - m_d["mae"], 4),
            "relative_improvement": round(float((m_base["mae"] - m_d["mae"]) / m_base["mae"]), 4)
            if np.isfinite(m_base["mae"]) else np.nan,
        }

    # ------------------------------------------------------------------ #
    # stratification (diameter, persistence vs XGBoost)
    # ------------------------------------------------------------------ #
    te["_persist_err"] = (te["target_wsmDia"] - te["base_wsmDia"]).abs()
    te["_xgb_err"] = (te["target_wsmDia"] - xgb_pred[:, DIMENSIONS.index("wsmDia")]).abs()
    strat = {}
    strat["distance_available"] = te.groupby("distance_available", dropna=False).apply(
        lambda g: {"n": int(len(g)),
                   "persistence_mae": round(float(g["_persist_err"].mean()), 4),
                   "xgb_mae": round(float(g["_xgb_err"].mean()), 4)}).to_dict()
    for col, edges in BAND_EDGES.items():
        if col not in te.columns:
            continue
        ser = te[col].apply(lambda v: _band(v, edges))
        strat[col] = te.groupby(ser).apply(
            lambda g: {"n": int(len(g)),
                       "persistence_mae": round(float(g["_persist_err"].mean()), 4),
                       "xgb_mae": round(float(g["_xgb_err"].mean()), 4)}).to_dict()

    results = {
        "task": "clean degradation benchmark (Phase 3C re-establishment)",
        "status": "diagnostic benchmark; historical 17.95mm INVALID (alignment bug)",
        "n_train": n_train,
        "n_test": n_te,
        "split": "chronological 80/20, frozen cohort",
        "frozen_cohort": "model_datasets/v3c/clean_benchmark_cohort.parquet",
        "seed": SEED,
        "models": ["persistence", "historical_rate", "ridge", "xgb"],
        "baselines": baselines,
        "ml": ml,
        "contamination": contamination,
        "distance_ablation": distance,
        "stratification": strat,
    }
    # normalize strat keys to strings for JSON
    results["stratification"] = {k: {str(ks): kv for ks, kv in v.items()}
                                 for k, v in strat.items()}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "clean_degradation_benchmark_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(f"train={n_train} test={n_te}")
    for d in DIMENSIONS:
        print(f"{d:18s} persist={baselines[d]['persistence']['mae']:.4f} "
              f"rate={baselines[d]['historical_rate']['mae']:.4f} "
              f"ridge={ml[d]['ridge']['mae']:.4f} xgb={ml[d]['xgb']['mae']:.4f} "
              f"| contam={contamination[d]['mae_change_from_cleaning']:+.4f} "
              f"dist={distance[d]['xgb_mae_with_distance']:.4f} "
              f"(delta {distance[d]['delta_mae']:+.4f})")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
