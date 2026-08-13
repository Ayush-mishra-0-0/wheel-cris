"""Layer 5 - persist turning-probability (P(turn)) serving models.

Trains the exact C1 XGB config from run_turn_probability_benchmark.py per
horizon (30/60/90) on the v5 turn_probability substrate TRAIN split, and
persists the fitted model + OrdinalEncoder + feature column order so the
FastAPI backend can predict turning probability for ANY wheelset anchor.

P(turn) = historical maintenance/turning behaviour, NOT engineering-limit
risk. Served predictions must be labelled as such.

Output:
  models/phase5/serving/turn_probability/model_<H>d.joblib
  models/phase5/serving/turn_probability/encoder.joblib
  models/phase5/serving/turn_probability/features.json
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "model_datasets" / "v5" / "turn_probability.parquet"
OUT = ROOT / "models" / "phase5" / "serving" / "turn_probability"

HORIZONS = (30, 60, 90)
SEED = 42

NUM_FEATS = [
    "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
    "mean_wsmFlangeThickness", "mean_wsmWheelGauge",
    "ph5_wsmFlange_rate_per_day_30d", "ph5_wsmFlange_rate_per_day_90d",
    "ph5_wsmThread_rate_per_day_30d", "ph5_wsmThread_rate_per_day_90d",
    "wsmRoot_rate_per_day_30d", "wsmRoot_rate_per_day_90d",
    "wsmDia_rate_per_day_30d", "wsmDia_rate_per_day_90d",
    "days_since_turning", "distance_since_turning_km",
    "days_since_last_inspection", "wheel_age_days_proxy",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d",
    "km_last_30d", "km_last_90d",
    "rtis_reporting_coverage_pct", "distance_per_day_km",
    "n_prior_turns", "segment_index",
    "axle_position_1_6", "wheel_position_1_12", "wheel_profile_2class",
]
CAT_FEATS = ["LocoType", "home_shed", "defect_zone", "shed_any"]


def build_matrix(df: pd.DataFrame, enc=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA", "<NA>": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(cat)
    else:
        Xc = enc.transform(cat)
    return np.hstack([Xn, Xc]), enc


def main() -> None:
    df = pd.read_parquet(DATA)
    is_train = df["split"].eq("train").to_numpy()
    train_cutoff = pd.to_datetime(df.loc[is_train, "anchor_ts"]).max()

    OUT.mkdir(parents=True, exist_ok=True)
    cat_all = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA", "<NA>": "NA"})
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    Xc_full = enc.fit_transform(cat_all)
    joblib.dump(enc, OUT / "encoder.joblib")
    (OUT / "features.json").write_text(
        json.dumps({"num_feats": NUM_FEATS, "cat_feats": CAT_FEATS,
                    "horizons": list(HORIZONS),
                    "train_cutoff": str(train_cutoff.date()),
                    "n_train_rows": int(is_train.sum())}, indent=2) + "\n",
        encoding="utf-8")

    manifest = {"task": "phase 5 layer 5 turning-probability serving models",
                "pointer": "P(turn) = historical maintenance behaviour, NOT engineering-limit risk",
                "models": []}
    for H in HORIZONS:
        ycol = df[f"turned_{H}d"].to_numpy(dtype=float)
        yok = np.isfinite(ycol)
        tr = is_train & yok
        Xtr = np.hstack([df.loc[tr, NUM_FEATS].to_numpy(dtype=float), Xc_full[tr]])
        ytr = ycol[tr]
        m = XGBClassifier(n_estimators=400, learning_rate=0.08, max_depth=6,
                          subsample=0.85, colsample_bytree=0.85,
                          tree_method="hist", random_state=SEED, verbosity=0,
                          eval_metric="logloss")
        m.fit(Xtr, ytr)
        path = OUT / f"model_{H}d.joblib"
        joblib.dump(m, path)
        manifest["models"].append({
            "horizon": H, "path": path.name,
            "n_train": int(len(ytr)),
            "turn_rate_train": round(float(ytr.mean()), 4)})
        print(f"P(turn) {H}d  train={len(ytr):,} saved")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
