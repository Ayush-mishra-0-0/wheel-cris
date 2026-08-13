"""Phase 3B - conformal prediction comparison on next-state degradation.

Three interval methods on the SAME chronological split (60% train / 20%
calibration / 20% test) so comparison is apples-to-apples:

  (a) plain quantile regression      - XGBoost reg:quantileerror 10/90
  (b) CQR-quantile (conformalized)   - plain quantile band widened by the
                                       conformal score quantile from calibration
  (c) CQR-mean (split conformal)     - mean model, band = +/- conformal width
                                       from absolute-residual quantile

Conformal guarantee: with a well-behaved calibration set, the band covers the
test actual with probability >= (1-alpha) in expectation, distribution-free.
We report empirical coverage + mean/p90 width per method per dimension.

Reset-crossing pairs excluded (within-life evolution only), same as before.
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


def _quantile_model():
    import xgboost as xgb
    lo = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=ALPHA,
                          n_estimators=250, learning_rate=0.05, max_depth=6,
                          n_jobs=-1, random_state=SEED)
    hi = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=1 - ALPHA,
                          n_estimators=250, learning_rate=0.05, max_depth=6,
                          n_jobs=-1, random_state=SEED)
    return lo, hi


def _conformal_quantile(scores, alpha):
    """Finite-sample conformal quantile (split conformal).

    Returns the smallest q such that at least ceil((n+1)(1-alpha)) of the
    calibration scores are <= q (1-indexed rank). Scores may be negative for
    rows inside the band (CQR), so we take the HIGH order statistic.
    """
    scores = np.asarray(scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    n = len(scores)
    if n == 0:
        return 0.0
    rank = int(np.ceil((n + 1) * (1 - alpha)))
    rank = max(1, min(rank, n))
    sorted_s = np.sort(scores)
    return float(sorted_s[rank - 1])


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
    n_tr = int(0.60 * len(wear))
    n_cal = int(0.20 * len(wear))
    tr_idx = order < n_tr
    cal_idx = (order >= n_tr) & (order < n_tr + n_cal)
    te_idx = order >= n_tr + n_cal

    Xtr_enc, encoders = _label_encode_cats(wear.loc[tr_idx, FEATURE_COLUMNS])
    Xcal_enc, _ = _label_encode_cats(wear.loc[cal_idx, FEATURE_COLUMNS], encoders)
    Xte_enc, _ = _label_encode_cats(wear.loc[te_idx, FEATURE_COLUMNS], encoders)
    for c in QUALITY_COLUMNS:
        for enc in (Xtr_enc, Xcal_enc, Xte_enc):
            enc[c + "_code"] = enc[c].fillna("MISSING").map(
                {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
                 "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}).astype(float)
    num_cols = STATE_COLUMNS + EXPOSURE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]
    Xtr = Xtr_enc[num_cols].astype(float).fillna(0.0)
    Xcal = Xcal_enc[num_cols].astype(float).fillna(0.0)
    Xte = Xte_enc[num_cols].astype(float).fillna(0.0)

    methods = ["plain_quantile", "cqr_quantile", "cqr_mean"]
    results = {}
    for d in DIMENSIONS:
        ytr = wear.loc[tr_idx, f"target_{d}"].to_numpy(dtype=float)
        ycal = wear.loc[cal_idx, f"target_{d}"].to_numpy(dtype=float)
        yte = wear.loc[te_idx, f"target_{d}"].to_numpy(dtype=float)
        f_tr = np.isfinite(ytr)
        f_cal = np.isfinite(ycal)
        f_te = np.isfinite(yte)

        lo, hi = _quantile_model()
        lo.fit(Xtr[f_tr], ytr[f_tr])
        hi.fit(Xtr[f_tr], ytr[f_tr])
        lo_cal = lo.predict(Xcal[f_cal])
        hi_cal = hi.predict(Xcal[f_cal])
        lo_te = lo.predict(Xte[f_te])
        hi_te = hi.predict(Xte[f_te])

        # (a) plain quantile
        cov_a = ((yte[f_te] >= lo_te) & (yte[f_te] <= hi_te)).mean()
        width_a = hi_te - lo_te

        # (b) CQR-quantile: calibrate max(lo-y, y-hi) on calibration set
        scores_b = np.maximum(lo_cal - ycal[f_cal], ycal[f_cal] - hi_cal)
        q_b = _conformal_quantile(scores_b, ALPHA)
        lo_b = lo_te - q_b
        hi_b = hi_te + q_b
        cov_b = ((yte[f_te] >= lo_b) & (yte[f_te] <= hi_b)).mean()
        width_b = hi_b - lo_b

        # (c) CQR-mean: mean model + absolute-residual conformal width
        mean_m = xgb.XGBRegressor(n_estimators=250, learning_rate=0.05, max_depth=6,
                                  n_jobs=-1, random_state=SEED)
        mean_m.fit(Xtr[f_tr], ytr[f_tr])
        mu_cal = mean_m.predict(Xcal[f_cal])
        scores_c = np.abs(ycal[f_cal] - mu_cal)
        q_c = _conformal_quantile(scores_c, ALPHA)
        mu_te = mean_m.predict(Xte[f_te])
        cov_c = ((yte[f_te] >= mu_te - q_c) & (yte[f_te] <= mu_te + q_c)).mean()
        width_c = 2 * q_c

        results[d] = {
            "n_train": int(f_tr.sum()), "n_cal": int(f_cal.sum()), "n_test": int(f_te.sum()),
            "methods": {
                "plain_quantile": {
                    "coverage": round(float(cov_a), 4),
                    "mean_width_mm": round(float(width_a.mean()), 4),
                    "p90_width_mm": round(float(np.quantile(width_a, 0.90)), 4),
                    "conformal_shift_mm": 0.0,
                },
                "cqr_quantile": {
                    "coverage": round(float(cov_b), 4),
                    "mean_width_mm": round(float(width_b.mean()), 4),
                    "p90_width_mm": round(float(np.quantile(width_b, 0.90)), 4),
                    "conformal_shift_mm": round(float(q_b), 4),
                },
                "cqr_mean": {
                    "coverage": round(float(cov_c), 4),
                    "mean_width_mm": round(float(width_c), 4),
                    "p90_width_mm": round(float(np.quantile(np.full(f_te.sum(), width_c), 0.90)), 4),
                    "conformal_shift_mm": round(float(q_c), 4),
                },
            },
        }
        print(f"{d:18s} plain={cov_a:.3f}/{width_a.mean():.3f}mm  "
              f"CQR-q={cov_b:.3f}/{width_b.mean():.3f}mm (shift {q_b:.3f})  "
              f"CQR-mean={cov_c:.3f}/+/-{q_c:.3f}mm")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "conformal_comparison.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Phase 3B - Conformal prediction comparison",
        "",
        "Same chronological split (60/20/20 train/calibration/test) for all methods.",
        "Target: 80% coverage.",
        "",
        "| Dimension | Method | Coverage | Mean width (mm) | p90 width (mm) | Conformal shift (mm) |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for d in DIMENSIONS:
        for meth, r in results[d]["methods"].items():
            lines.append(f"| {d} | {meth} | {r['coverage']:.1%} | {r['mean_width_mm']:.3f} "
                         f"| {r['p90_width_mm']:.3f} | {r['conformal_shift_mm']:.3f} |")
    lines += [
        "",
        "## Reading this",
        "",
        "- plain_quantile: honest but no formal guarantee (can be slightly wide).",
        "- cqr_quantile: conformal width added to the quantile band -> guarantees",
        "  ~>=80% coverage distribution-free; watch the width cost.",
        "- cqr_mean: simple symmetric +/- band with a conformal guarantee; widths",
        "  should be compared against the quantile methods.",
        "- If CQR coverage lands near 80% with modest width increase, it is the",
        "  defensible interval for the paper (guarantee + tightness).",
    ]
    (OUTPUT / "conformal_comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
