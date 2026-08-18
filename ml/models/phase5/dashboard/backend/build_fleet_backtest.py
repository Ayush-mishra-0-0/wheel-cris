"""Layer 5 - build consolidated fleet backtest metrics.

Reads the stored static benchmarks:
  - degradation_benchmark.json       (MAE/RMSE/R2 per dim@H over the test set)
  - turn_probability_benchmark.json  (ROC-AUC, PR-AUC, Brier, ECE, capture@top)
and appends model-vs-actual implausibility diagnostics computed directly on the
degradation substrate TEST set (point-in-time split) with the SAME serving
models the dashboard uses.

Implausibility diagnostics (reported, not clipped):
  wsmDia:  predicted diameter > current (+0.001)        -> increasing_diameter
  root/flange/thread: predicted value < current - 0.05   -> wear_improving
Both model rate and ACTUAL baseline rate are reported so the user can judge how
far the model diverges from real within-segment physics.

Output: models/experiments/v5/fleet_backtest.json
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EXP = ROOT / "models" / "experiments" / "v5"
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
SERV = ROOT / "models" / "phase5" / "serving" / "degradation"
RATE = ROOT / "models" / "phase5" / "serving" / "degradation_rate"

HORIZONS = (30, 90, 180)
DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
WEAR_DIMS = ("wsmRoot", "wsmFlange", "wsmThread")
WEAR_BETTER_TOL = 0.25      # re-derived from same-day repeatability floor (root MAD ~0.2)
DIA_INC_TOL = 1.5           # re-derived from same-day repeatability floor (dia MAD 1.5)


def delta_for(dim, h, X, Xr, models, rate_models, champ):
    """Model-of-record delta mirroring service._horizon_deltas."""
    choice = champ.get("dim_model_of_record", {})
    if choice.get(dim) == "wear_rate" and rate_models and champ.get("decay_k"):
        rate = float(rate_models[dim].predict(Xr)[0])
        if not np.isfinite(rate):
            return np.full(len(Xr), np.nan)
        r = np.clip(rate, None, 0.0) if dim == "wsmDia" else np.clip(rate, 0.0, None)
        return champ.get("decay_k", {}).get(f"{dim}_{h}d", 1.0) * r * h
    return models[dim][h].predict(X)


def main() -> None:
    d = pd.read_parquet(DATA)
    te = d[d["split"].eq("test")].copy()
    feats = json.loads((SERV / "features.json").read_text())
    NUM, CAT = feats["num_feats"], feats["cat_feats"]
    enc = joblib.load(SERV / "encoder.joblib")
    cat = te[CAT].astype(str).replace({"nan": "NA", "None": "NA"})
    Xc = enc.transform(cat)

    champ = {}
    rate_models = {}
    Xr = None
    if (RATE / "champion.json").exists():
        champ = json.loads((RATE / "champion.json").read_text())
        rate_feats = json.loads((RATE / "features.json").read_text())
        if RATE.exists():
            rate_enc = joblib.load(RATE / "encoder.joblib")
            Xr = np.hstack([te[rate_feats["num_feats"]].to_numpy(float),
                            rate_enc.transform(te[rate_feats["cat_feats"]].astype(str)
                                               .replace({"nan": "NA", "None": "NA"}))])
            rate_models = {dim: joblib.load(RATE / f"model_{dim}.joblib") for dim in DIMM}

    models = {dim: {h: joblib.load(SERV / f"model_{dim}_{h}d.joblib")
                    for h in HORIZONS} for dim in DIMM}

    diag = {}
    for dim in DIMM:
        diag[dim] = {}
        for H in HORIZONS:
            el = te[f"eligible_{dim}_{H}d"] & te[f"tgt_{dim}_{H}d"].notna()
            if el.sum() == 0:
                diag[dim][f"{H}d"] = None
                continue
            Xn = te.loc[el, NUM].to_numpy(float)
            X = np.hstack([Xn, Xc[el.to_numpy()]])
            Xrate = Xr[el.to_numpy()] if Xr is not None else None
            cur = te.loc[el, f"mean_{dim}"].to_numpy(float)
            delta = delta_for(dim, H, X, Xrate, models, rate_models, champ)
            pred = cur + delta
            tgt = te.loc[el, f"tgt_{dim}_{H}d"].to_numpy(float)
            fin = np.isfinite(pred) & np.isfinite(cur)
            if dim == "wsmDia":
                actual_inc = float(np.mean(tgt > cur + DIA_INC_TOL)) if len(tgt) else 0.0
                model_inc = float(np.mean(pred[fin] > cur[fin] + DIA_INC_TOL)) if fin.any() else 0.0
                diag[dim][f"{H}d"] = {
                    "n": int(el.sum()),
                    "flag": "increasing_diameter",
                    "actual_rate": round(actual_inc * 100, 2),
                    "model_rate": round(model_inc * 100, 2),
                }
            else:
                actual_imp = float(np.mean(tgt < cur - WEAR_BETTER_TOL)) if len(tgt) else 0.0
                model_imp = float(np.mean(pred[fin] < cur[fin] - WEAR_BETTER_TOL)) if fin.any() else 0.0
                diag[dim][f"{H}d"] = {
                    "n": int(el.sum()),
                    "flag": "wear_improving",
                    "actual_rate": round(actual_imp * 100, 2),
                    "model_rate": round(model_imp * 100, 2),
                }

    summary = {
        "task": "phase 5 layer 5 fleet-level temporal backtest",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "split": "temporal point-in-time (train_cutoff preserved from substrate)",
        "target_mode": ("delta (serving models regress change; level = anchor + delta). "
                        "Per-dim model of record follows serving/degradation_rate/champion.json "
                        "('wear_rate' integrates delta = decay_k * rate * horizon)."),
        "model_of_record": champ.get("dim_model_of_record", {}),
        "implausibility_note": ("Implausibility flags are reported explicitly, never clipped. "
                                "Model over-prediction vs actual within-segment physics is surfaced below."),
        "degradation": json.loads((EXP / "degradation_benchmark.json").read_text()),
        "turn_probability": json.loads((EXP / "turn_probability_benchmark.json").read_text()),
        "implausibility_diagnostics": diag,
    }
    (EXP / "fleet_backtest.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    for dim in DIMM:
        for H in HORIZONS:
            row = diag[dim].get(f"{H}d")
            if row:
                print(f"{dim} {H}d: actual={row['actual_rate']}% model={row['model_rate']}% ({row['flag']})")
    print(EXP.relative_to(ROOT))


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    main()
