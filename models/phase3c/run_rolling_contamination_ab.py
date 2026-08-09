"""Phase 3C - rolling contamination A/B + cadence honesty (companion to
run_diagnostic_forensics.py).

Per rolling window (expanding train, disjoint test windows over the FULL
substrate incl. boundary rows):
  - Arm FULL : train on ALL rows (incl. replacement/reset boundary pairs)
  - Arm CLEAN: train on within-lifecycle rows only
evaluated on the same test ids per window.

Also reports cadence honesty (median interval, IQR) and zero-delta fraction
(target == base) per dimension on the frozen test cohort.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))

from degradation_eval import (  # noqa: E402
    ROW_ID_COL, DIMENSIONS, add_targets_and_bases, _reg_metrics,
)
from run_clean_degradation_benchmark import _base_num_cols, _prepare  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / "model_datasets" / "v3c" / "clean_benchmark_pairs.parquet"
COHORT = ROOT / "model_datasets" / "v3c" / "clean_benchmark_cohort.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3c"
NWINS = 4
SEED = 42


def fit_xgb_mask(w_sorted, tr_mask, te_mask, d, cols, seed):
    from xgboost import XGBRegressor
    Xtr = _prepare(w_sorted, cols).loc[tr_mask].to_numpy()
    Xte = _prepare(w_sorted, cols).loc[te_mask].to_numpy()
    y = w_sorted[f"target_{d}"].to_numpy(dtype=float)
    ytr = y[tr_mask]
    yte = y[te_mask]
    fin = np.isfinite(ytr)
    mod = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                       subsample=1.0, colsample_bytree=1.0, random_state=seed,
                       n_jobs=-1, tree_method="hist")
    mod.fit(Xtr[fin], ytr[fin])
    return _reg_metrics(yte, mod.predict(Xte))


def main() -> None:
    raw = pd.read_parquet(SUBSTRATE)
    raw = add_targets_and_bases(raw)
    w_s = raw.sort_values("measurement_timestamp").reset_index(drop=True)
    cols = _base_num_cols()
    ids = w_s[ROW_ID_COL].to_numpy()
    ok_clean = w_s["within_lifecycle"].to_numpy()

    n_rows = len(ids)
    per = n_rows // NWINS
    roll_ab = {}
    for i in range(NWINS):
        te_ids = set(ids[i * per:(i + 1) * per])
        tr_ids = set(ids[: i * per])
        tem = w_s[ROW_ID_COL].isin(te_ids).to_numpy()
        trm = ~tem
        trm_clean = trm & ok_clean
        win = {"n": int(tem.sum())}
        for d in DIMENSIONS:
            m_full = fit_xgb_mask(w_s, trm, tem, d, cols, SEED)
            m_clean = fit_xgb_mask(w_s, trm_clean, tem, d, cols, SEED)
            win[d] = {"full_mae": m_full["mae"], "clean_mae": m_clean["mae"],
                      "delta_full_minus_clean": round(m_full["mae"] - m_clean["mae"], 4)}
        roll_ab[f"win{i}"] = win

    # cadence + zero-delta honesty on the frozen within-life test cohort
    df = pd.read_parquet(SUBSTRATE)
    df = df[df.within_lifecycle].copy()
    df = add_targets_and_bases(df)
    c = pd.read_parquet(COHORT)
    test_ids = set(c.loc[c.split == "test", ROW_ID_COL])
    t = df[df[ROW_ID_COL].isin(test_ids)]
    cad = {
        "n": int(len(t)),
        "interval_days_median": float(t["interval_days"].median()),
        "interval_days_q25": float(t["interval_days"].quantile(0.25)),
        "interval_days_q75": float(t["interval_days"].quantile(0.75)),
        "interval_days_gt_90d_frac": round(float((t["interval_days"] > 90).mean()), 4),
    }
    zero = {}
    for d in DIMENSIONS:
        tt = t[f"target_{d}"].to_numpy(dtype=float)
        bb = t[f"base_{d}"].to_numpy(dtype=float)
        ok = np.isfinite(tt) & np.isfinite(bb)
        zero[d] = {
            "n": int(ok.sum()),
            "frac_target_equals_base": round(float(np.mean(tt[ok] == bb[ok])), 4),
            "frac_abs_delta_lt_0p01mm": round(float(np.mean(np.abs(tt[ok] - bb[ok]) < 0.01)), 4),
        }

    out = {
        "task": "Phase 3C rolling contamination A/B + cadence honesty",
        "n_windows": NWINS,
        "seed": SEED,
        "rolling_contamination": roll_ab,
        "cadence_test_cohort": cad,
        "zero_delta_frac_test_cohort": zero,
    }
    OUT = OUTPUT / "diagnostic_rolling_ab_results.json"
    OUT.write_text(json.dumps(out, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    print(OUT)
    print("cadence:", cad)
    print("zero_delta:", zero)
    for k, v in roll_ab.items():
        print(k, v)


if __name__ == "__main__":
    main()