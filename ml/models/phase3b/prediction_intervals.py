"""Phase 3B - prediction intervals on next-state degradation.

Adds uncertainty to the next-state degradation model: for each dimension we fit
an 80% prediction interval (10th and 90th quantile regressors via XGBoost
quantile objective) alongside the point prediction, on the SAME chronological
split as the next-state model. We then measure empirical coverage on held-out
data: what fraction of actual next measurements fall inside the interval.

A well-calibrated interval should cover ~80% of held-out actuals. Coverage well
below 80% means the model is overconfident (intervals too narrow) - an honest
check that the accuracy claim carries a confidence band.

Reset-crossing pairs excluded (within-life evolution only), matching the
degradation model.
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
ALPHA = 0.10  # 80% interval

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
    wear = pairs.loc[~pairs["crosses_reset"]].dropna(subset=["next_record_id"]).copy()

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

    results = {}
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
        covered = ((yt >= lo_te) & (yt <= hi_te)).mean()
        width = np.mean(hi_te - lo_te)
        width_90 = float(np.quantile(hi_te - lo_te, 0.90))
        results[d] = {
            "n_test": int(finite_te.sum()),
            "empirical_coverage": round(float(covered), 4),
            "target_coverage": 0.80,
            "coverage_gap_pts": round(float(covered - 0.80), 4),
            "mean_interval_width_mm": round(float(width), 4),
            "p90_interval_width_mm": round(width_90, 4),
            "mean_abs_error_point": round(float(np.mean(np.abs(
                yt - (lo_te + hi_te) / 2))), 4),
        }
        print(f"{d:18s} coverage={covered:.3f} (target 0.80) gap={covered-0.80:+.3f} "
              f"mean width={width:.3f} mm p90 width={width_90:.3f}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "prediction_interval_coverage.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Phase 3B - Prediction intervals on next-state degradation",
        "",
        "80% prediction intervals (10th/90th quantile XGBoost) on the next measured",
        "state per dimension, measured on held-out chronological data.",
        "",
        "| Dimension | n | Empirical coverage | Target | Gap (pts) | Mean width (mm) | p90 width (mm) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for d in DIMENSIONS:
        r = results[d]
        lines.append(f"| {d} | {r['n_test']:,} | {r['empirical_coverage']:.1%} | "
                     f"{r['target_coverage']:.0%} | {r['coverage_gap_pts']:+.3f} | "
                     f"{r['mean_interval_width_mm']:.3f} | {r['p90_interval_width_mm']:.3f} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- Coverage near 80% = the uncertainty band is honest (well calibrated).",
        "- Coverage well below 80% = intervals too narrow (overconfident).",
        "- Width in mm is the practical uncertainty: e.g. diameter interval +/- X mm.",
        "- Same chronological split and reset exclusion as the degradation model.",
    ]
    (OUTPUT / "prediction_interval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
