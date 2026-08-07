"""Phase 3B - conditional coverage by wheel group (turning vs normal).

Replicates the prediction-interval setup and splits coverage by whether the
equipment EVER recorded a turning in the engineering-state data. Answers:
"are intervals equally honest for wheels that get turned vs wheels that don't?"
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "model_datasets" / "v3b"
OUTPUT = ROOT / "models" / "experiments" / "v3b" / "prediction_intervals"
SEED = 42
ALPHA = 0.10

DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot"]
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


def _label_encode_cats(df, encoders=None):
    out = df.copy()
    enc = encoders if encoders is not None else {}
    for c in CATEGORICAL_COLUMNS:
        if encoders is None:
            vals = out[c].dropna().astype(str).unique()
            enc[c] = {v: i for i, v in enumerate(sorted(vals))}
        out[c] = out[c].astype(str).map(enc[c]).astype(float)
    return out, enc


def main() -> None:
    import xgboost as xgb

    pairs = pd.read_parquet(DATA_DIR / "degradation_pairs.parquet")
    # equipment-level "ever turned" flag from ALL pairs (including reset rows)
    ever_turned = (pairs.groupby("wheelset_equipment_id")["turning_record_at_measurement"]
                   .max().gt(0))
    wear = pairs.loc[~pairs["crosses_reset"]].dropna(subset=["next_record_id"]).copy()
    wear["ever_turned"] = wear["wheelset_equipment_id"].map(ever_turned)

    for d in DIMENSIONS:
        t1, t2 = f"{d}1", f"{d}2"
        v1 = wear[f"{t1}_quality"].eq("OBSERVED_VALID")
        v2 = wear[f"{t2}_quality"].eq("OBSERVED_VALID")
        wear[f"target_{d}"] = np.where(
            v1 & v2, (wear[f"next_{t1}"] + wear[f"next_{t2}"]) / 2.0,
            np.where(v1, wear[f"next_{t1}"], np.where(v2, wear[f"next_{t2}"], np.nan)))

    wear = wear.sort_values("measurement_timestamp")
    order = np.arange(len(wear))
    tr_idx = order < 0.8 * len(wear)
    te_idx = order >= 0.8 * len(wear)

    Xtr_enc, encoders = _label_encode_cats(wear.loc[tr_idx, FEATURE_COLUMNS])
    Xte_enc, _ = _label_encode_cats(wear.loc[te_idx, FEATURE_COLUMNS], encoders)
    for c in QUALITY_COLUMNS:
        Xtr_enc[c + "_code"] = Xtr_enc[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
        Xte_enc[c + "_code"] = Xte_enc[c].fillna("MISSING").map(
            {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
             "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    num_cols = STATE_COLUMNS + EXPOSURE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]
    Xtr = Xtr_enc[num_cols].astype(float).fillna(0.0)
    Xte = Xte_enc[num_cols].astype(float).fillna(0.0)

    ever_te = wear.loc[te_idx, "ever_turned"].to_numpy()

    table = []
    for d in DIMENSIONS:
        ytr = wear.loc[tr_idx, f"target_{d}"].to_numpy(dtype=float)
        yte = wear.loc[te_idx, f"target_{d}"].to_numpy(dtype=float)
        finite_tr = np.isfinite(ytr)
        finite_te = np.isfinite(yte)

        lo = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=ALPHA,
                              n_estimators=250, learning_rate=0.05, max_depth=6,
                              n_jobs=-1, random_state=SEED)
        hi = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=1 - ALPHA,
                              n_estimators=250, learning_rate=0.05, max_depth=6,
                              n_jobs=-1, random_state=SEED)
        lo.fit(Xtr[finite_tr], ytr[finite_tr])
        hi.fit(Xtr[finite_tr], ytr[finite_tr])

        lo_te = lo.predict(Xte[finite_te])
        hi_te = hi.predict(Xte[finite_te])
        yt = yte[finite_te]
        et = ever_te[finite_te]

        covered = (yt >= lo_te) & (yt <= hi_te)
        width = hi_te - lo_te

        row = {"dimension": d}
        row["target_coverage"] = 0.80
        row["actual_coverage"] = round(float(covered.mean()), 4)
        row["mean_width_mm"] = round(float(width.mean()), 3)
        for grp, mask in (("turning", et), ("normal", ~et)):
            if mask.sum() < 30:
                row[f"{grp}_coverage"] = None
                row[f"{grp}_n"] = int(mask.sum())
            else:
                row[f"{grp}_coverage"] = round(float(covered[mask].mean()), 4)
                row[f"{grp}_n"] = int(mask.sum())
        table.append(row)
        print(f"{d:18s} overall={row['actual_coverage']:.3f} "
              f"turning={row['turning_coverage']} (n={row['turning_n']}) "
              f"normal={row['normal_coverage']} (n={row['normal_n']})")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "conditional_coverage_by_group.json").write_text(
        json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
