"""Layer 5 - persist degradation serving models.

Trains the exact C1 XGB config from run_degradation_benchmark.py per
(target dim, horizon) on the v5 substrate TRAIN split (frozen PIT split,
labels known at the train cutoff), and persists the fitted model + the
OrdinalEncoder + the feature column order so the FastAPI backend can predict
for ANY wheelset (including Loco 37597, which is outside the substrate).

TARGET_MODE = "delta": the models regress the CHANGE over the horizon (delta =
horizon state - anchor state), matching run_degradation_benchmark.py. At serve
time the backend reconstructs pred = anchor_mean + delta. This removes the
between-wheel LEVEL dominance that inflated R2 in the old level regression.

Output:
  models/phase5/serving/degradation/*.joblib  (model_<dim>_<H>d.joblib)
  models/phase5/serving/degradation/encoder.joblib
  models/phase5/serving/degradation/features.json
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
OUT = ROOT / "models" / "phase5" / "serving" / "degradation"

TARGET_MODE = "delta"
HORIZONS = (30, 90, 180)
TARGET_DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
SEED = 42

NUM_FEATS = [
    "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
    "mean_wsmFlangeThickness", "mean_wsmWheelGauge",
    "ph5_wsmFlange_rate_per_day_30d", "ph5_wsmFlange_rate_per_day_90d",
    "ph5_wsmFlange_rate_per_day_180d",
    "ph5_wsmThread_rate_per_day_30d", "ph5_wsmThread_rate_per_day_90d",
    "ph5_wsmThread_rate_per_day_180d",
    "wsmRoot_rate_per_day_30d", "wsmRoot_rate_per_day_90d",
    "wsmDia_rate_per_day_30d", "wsmDia_rate_per_day_90d",
    "days_since_turning", "distance_since_turning_km",
    "days_since_last_inspection", "wheel_age_days_proxy",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d", "inspection_count_180d",
    "km_last_30d", "km_last_90d", "km_last_180d",
    "rtis_reporting_coverage_pct", "distance_per_day_km",
    "n_prior_turns", "segment_index",
    "axle_position_1_6", "wheel_position_1_12", "wheel_profile_2class",
]
CAT_FEATS = ["LocoType", "home_shed", "defect_zone", "shed_any"]


def build_matrix(df: pd.DataFrame, enc=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(cat)
    else:
        Xc = enc.transform(cat)
    return np.hstack([Xn, Xc]), enc


def main() -> None:
    df = pd.read_parquet(DATA)
    is_train = df["split"].eq("train").to_numpy()
    train_cutoff = pd.to_datetime(df.loc[is_train, "measurement_timestamp"]).max()
    tgt_arr = {H: pd.to_datetime(df[f"tgt_obs_ts_{H}d"]).to_numpy(dtype="datetime64[us]")
               for H in HORIZONS}

    Xn_all = df.loc[is_train, NUM_FEATS].to_numpy(dtype=float)
    cat = df.loc[is_train, CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    Xc_all = enc.fit_transform(cat)
    cat_all = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    Xc_full = enc.transform(cat_all)
    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump(enc, OUT / "encoder.joblib")
    (OUT / "features.json").write_text(
        json.dumps({"num_feats": NUM_FEATS, "cat_feats": CAT_FEATS,
                    "horizons": list(HORIZONS), "target_dims": list(TARGET_DIMS),
                    "train_cutoff": str(train_cutoff.date()),
                    "n_train_rows": int(is_train.sum())}, indent=2) + "\n",
        encoding="utf-8")

    manifest = {"task": "phase 5 layer 2 degradation serving models",
                "models": []}
    for dim in TARGET_DIMS:
        for H in HORIZONS:
            elig = df[f"eligible_{dim}_{H}d"].to_numpy()
            ycol = df[f"tgt_{dim}_{H}d"].to_numpy(dtype=float)
            cur = df[f"mean_{dim}"].to_numpy(dtype=float)
            yok = np.isfinite(ycol) & np.isfinite(cur)
            tr = is_train & elig & yok & (tgt_arr[H] <= train_cutoff)
            Xtr = np.hstack([df.loc[tr, NUM_FEATS].to_numpy(dtype=float),
                             Xc_full[tr]])
            ytr = ycol[tr] - cur[tr]  # delta target (TARGET_MODE)
            m = XGBRegressor(n_estimators=400, learning_rate=0.08, max_depth=6,
                             subsample=0.85, colsample_bytree=0.85,
                             tree_method="hist", random_state=SEED, verbosity=0)
            m.fit(Xtr, ytr)
            path = OUT / f"model_{dim}_{H}d.joblib"
            joblib.dump(m, path)
            manifest["models"].append({
                "dim": dim, "horizon": H, "path": path.name,
                "n_train": int(len(ytr)), "target": TARGET_MODE})
            print(f"{dim} {H}d  train={len(ytr):,} saved")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()