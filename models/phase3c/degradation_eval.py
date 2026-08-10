"""Phase 3C - alignment-safe degradation evaluation core.

Everything here is built around one invariant: the row identity is
`measurement_record_id`, and it is carried through every sort, filter, merge,
groupby, reset_index and split. Before any model fit, the caller must call
`assert_row_alignment(X, Y)` which verifies the feature rows and target rows
refer to exactly the same measurement pairs.

This module never fits models that consume X/Y built from different row orders.
It provides:

  - shared dimension/column constants (mirroring v3b);
  - target/base construction (next-state absolute mm) with row identity;
  - a chronological split returning SAME frozen test indices to all callers;
  - metric helpers (MAE/RMSE/R2/Spearman/N) that tolerate NaN targets;
  - persistence scoring (prediction = current state);
  - a point-in-time historical-rate baseline;
  - Ridge and XGBoost fit helpers.

REPLICATION NOTE: the historical v3b script computed Y/B on the parquet row
order then indexed them with post-sort positions while building X post-sort.
That misalignment produced the invalid 17.95 mm MAE. This module is the
replacement: it sorts once, carries row ids, and asserts alignment.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROW_ID_COL = "measurement_record_id"

DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot", "wsmWheelGauge"]
SIDES = ["1", "2"]
STATE_COLUMNS = [f"{d}{s}" for d in DIMENSIONS for s in SIDES]
QUALITY_COLUMNS = [f"{c}_quality" for c in STATE_COLUMNS]
OBSERVED = "OBSERVED_VALID"

# Exposure / categorical columns used by the v3b feature set (kept identical so
# the clean benchmark is directly comparable to the aligned Stage B result).
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


# --------------------------------------------------------------------------- #
# row-identity helpers
# --------------------------------------------------------------------------- #
def assert_row_alignment(x_row_ids: pd.Series | np.ndarray,
                         y_row_ids: pd.Series | np.ndarray) -> None:
    """Assert that feature rows and target rows refer to the SAME pairs in the
    SAME order. Raises ValueError otherwise. This is the guard that would have
    caught the 17.95 mm bug."""
    a = np.asarray(x_row_ids)
    b = np.asarray(y_row_ids)
    if a.shape != b.shape:
        raise ValueError(
            f"row-id shape mismatch: X {a.shape} vs Y {b.shape} — a sort/filter/"
            f"merge has dropped or duplicated rows without carrying the row id.")
    if not np.array_equal(a, b):
        mismatch = int(np.sum(a != b))
        raise ValueError(
            f"row-id MISALIGNMENT: {mismatch}/{len(a)} feature rows do not match "
            f"target rows. Refusing to fit on positionally-misaligned X/Y.")
    if a.size == 0:
        raise ValueError("row-id array is empty — refusing to fit on no rows.")


def _is_valid(q: pd.Series) -> pd.Series:
    return q.eq(OBSERVED)


# --------------------------------------------------------------------------- #
# target / base construction (absolute next-state, mm)
# --------------------------------------------------------------------------- #
def add_targets_and_bases(wear: pd.DataFrame) -> pd.DataFrame:
    """Add `target_{d}` (next valid within-life state) and `base_{d}` (current
    state) per dimension. Preserves row order and the row-id column. Uses the
    exact v3b OBSERVED_VALID rule: mean of both sides when both valid, else the
    single valid side, else NaN."""
    out = wear.copy()
    for d in DIMENSIONS:
        t1, t2 = f"{d}1", f"{d}2"
        v1 = _is_valid(out[f"{t1}_quality"])
        v2 = _is_valid(out[f"{t2}_quality"])
        n1 = _is_valid(out[f"next_{t1}_quality"])
        n2 = _is_valid(out[f"next_{t2}_quality"])
        out[f"target_{d}"] = np.where(
            n1 & n2, (out[f"next_{t1}"] + out[f"next_{t2}"]) / 2.0,
            np.where(n1, out[f"next_{t1}"], np.where(n2, out[f"next_{t2}"], np.nan)))
        out[f"base_{d}"] = np.where(
            v1 & v2, (out[t1] + out[t2]) / 2.0,
            np.where(v1, out[t1], np.where(v2, out[t2], np.nan)))
    return out


# --------------------------------------------------------------------------- #
# chronological split (single source of truth for the frozen test cohort)
# --------------------------------------------------------------------------- #
def chronological_split(wear: pd.DataFrame, test_frac: float = 0.2,
                        time_col: str = "measurement_timestamp",
                        cache_path: Path | None = None):
    """Return (wear_sorted, tr_mask, te_mask). Sorts ONCE by time, builds the
    masks on the sorted frame, and (optionally) persists the frozen row ids.

    All benchmark arms MUST call this and reuse the returned masks so every
    model is evaluated on the identical test cohort."""
    wear = wear.sort_values(time_col).reset_index(drop=True)
    order = np.arange(len(wear))
    split_at = int(len(wear) * (1.0 - test_frac))
    tr_mask = order < split_at
    te_mask = order >= split_at
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({ROW_ID_COL: wear[ROW_ID_COL].to_numpy(),
                      "split": np.where(tr_mask, "train", "test")}).to_parquet(cache_path, index=False)
    return wear, tr_mask, te_mask


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _reg_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = np.isfinite(y_true) & np.isfinite(y_pred)
    if valid.sum() < 10:
        return {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "spearman": np.nan, "n": int(valid.sum())}
    yt, yp = y_true[valid], y_pred[valid]
    mae = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    rho = np.nan if np.all(yp == yp[0]) else float(spearmanr(yt, yp)[0])
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4),
            "spearman": round(rho, 4), "n": int(valid.sum())}


def evaluate(test: pd.DataFrame, pred_col: str, target_col: str) -> dict:
    """Evaluate one prediction column against one target column on a test frame."""
    y_true = test[target_col].to_numpy(dtype=float)
    y_pred = test[pred_col].to_numpy(dtype=float)
    return _reg_metrics(y_true, y_pred)


def score_aligned(model_pred: np.ndarray, test: pd.DataFrame, target_col: str,
                  test_ids: np.ndarray) -> dict:
    """Alignment-safe evaluation: assert model predictions match test row ids
    before scoring."""
    assert_row_alignment(test_ids, test[ROW_ID_COL].to_numpy())
    y_true = test[target_col].to_numpy(dtype=float)
    return _reg_metrics(y_true, model_pred)


# --------------------------------------------------------------------------- #
# persistence baseline (first-class)
# --------------------------------------------------------------------------- #
def persistence_results(test: pd.DataFrame) -> dict:
    """Prediction = current measured state; target = next valid within-life
    state. Per dimension: MAE/RMSE/R2/Spearman/N."""
    out = {}
    for d in DIMENSIONS:
        m = _reg_metrics(test[f"target_{d}"].to_numpy(dtype=float),
                         test[f"base_{d}"].to_numpy(dtype=float))
        out[d] = {"unit": "mm", **m}
    return out


# --------------------------------------------------------------------------- #
# point-in-time historical-rate baseline
# --------------------------------------------------------------------------- #
def add_historical_rate_predictions(wear: pd.DataFrame,
                                    time_col: str = "measurement_timestamp") -> pd.DataFrame:
    """Point-in-time historical-rate baseline per dimension.

    predicted_delta_d = historical_rate_d(t) * interval_days
    predicted_next_d = base_d + predicted_delta_d

    historical_rate_d(t) = cumulative_valid_wear_d / cumulative_valid_days
    where both cumulative quantities use ONLY rows whose current measurement is
    at or before the prediction timestamp t (no future data, no lifetime
    statistics computed over the whole dataset).

    Wear_d per observed interval = base_d at that row MINUS target_d at that
    row? No — use the interval's own start/end change from the pair columns so
    the rate is defined per consecutive inspection. To keep this strictly
    point-in-time and simple, we compute the wheelset's mean per-day change
    from its OWN prior pairs only (info available at t).

    Falls back to persistence (delta = 0) when the wheelset has no prior valid
    interval at time t.
    """
    out = wear.copy().sort_values(["wheelset_equipment_id", time_col])
    out = out.reset_index(drop=True)
    pid = out["wheelset_equipment_id"]
    for d in DIMENSIONS:
        # per-interval observed change: next valid state minus current valid state
        chg = (out[f"target_{d}"] - out[f"base_{d}"])  # +ve = increase
        days = out["interval_days"].fillna(0.0)
        # only count intervals where both ends are valid
        t_ok = (out[f"target_{d}"].notna() & out[f"base_{d}"].notna()).astype(float)
        chg_v = chg.where(t_ok.eq(1.0)).fillna(0.0)
        days_v = days.where(t_ok.eq(1.0)).fillna(0.0)
        # cumulative within wheelset EXCLUDING current row (rate at t uses only
        # intervals that ended strictly before t; the current target is never in
        # the rate, so no target leakage).
        cum_chg = chg_v.groupby(pid).cumsum() - chg_v
        cum_days = days_v.groupby(pid).cumsum() - days_v
        prior_valid = cum_days.gt(0)
        rate = (cum_chg / cum_days).where(prior_valid)
        delta = rate * out["interval_days"]
        out[f"hist_rate_{d}"] = rate
        out[f"pred_{d}"] = np.where(
            prior_valid, out[f"base_{d}"] + delta.fillna(0.0), out[f"base_{d}"])
    return out


# --------------------------------------------------------------------------- #
# model helpers (fixed hyperparameters — no tuning)
# --------------------------------------------------------------------------- #
def fit_ridge(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray, alpha: float = 10.0):
    from sklearn.linear_model import Ridge
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return np.full(Xte.shape[0], np.nan)
    r = Ridge(alpha=alpha)
    r.fit(Xtr[fin], ytr[fin])
    return r.predict(Xte)


def fit_xgb(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray,
            seed: int = 42):
    from xgboost import XGBRegressor
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return np.full(Xte.shape[0], np.nan)
    m = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                     subsample=1.0, colsample_bytree=1.0, random_state=seed,
                     n_jobs=-1, tree_method="hist")
    m.fit(Xtr[fin], ytr[fin])
    return m.predict(Xte)


def label_encode_cats(df: pd.DataFrame, columns: list[str], encoders=None):
    out = df.copy()
    enc = encoders if encoders is not None else {}
    for c in columns:
        if encoders is None:
            vals = out[c].dropna().astype(str).unique()
            enc[c] = {v: i for i, v in enumerate(sorted(vals))}
        out[c] = out[c].astype(str).map(enc[c]).astype(float)
    return out, enc
