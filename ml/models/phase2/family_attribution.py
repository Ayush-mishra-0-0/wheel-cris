"""WS4 — family-level attribution on the v2.0 LightGBM champion.

Three complementary views, all on the grouped TEST split (no train leak):

  1. SHAP family attribution: sum |mean SHAP| per family from the persisted
     WS2 SHAP matrix, plus size-normalized mean (families have 2-25 features).
  2. Leave-one-in: single-family test RMSE (reuses WS5 forward step-1 results).
  3. Drop-family agreement: full-model vs leave-one-out predictions — Pearson
     correlation and prediction displacement (how much each family moves the
     model) — computed with fresh LOO fits on LightGBM.

Also reports per-row dominant-family SHAP fractions (which family drives the
largest absolute SHAP per row), tied to the WS3 worst-rows analysis.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.phase2.families import FAMILY_ORDER, feature_families  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"
SHAP_PATH = EXPERIMENTS_ROOT / "interpretability" / "experiment_0001" / "shap_values_test.parquet"
ABLATION_DIR = EXPERIMENTS_ROOT / "ablation"
OUT_DIR = EXPERIMENTS_ROOT / "family_attribution"
REGRESSION_LABEL = "next_interval_dia_delta_mm"
SEED = 42


def _lgb(seed: int):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=63,
                             subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                             random_state=seed, verbosity=-1)


def main() -> None:
    df = pd.read_parquet(DATASET_PATH)
    fams = feature_families()
    all_cols = [c for cols in fams.values() for c in cols]
    sh = pd.read_parquet(SHAP_PATH)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tr = df[df["split"] == "train"].reset_index(drop=True)
    te = df[df["split"] == "test"].reset_index(drop=True)
    ytr, yte = tr[REGRESSION_LABEL], te[REGRESSION_LABEL]

    # --- 1. SHAP family attribution (from WS2 matrix) ---
    mean_abs = sh.abs().mean()
    fam_sum = {f: float(mean_abs[[c for c in fams[f] if c in mean_abs.index]].sum())
               for f in FAMILY_ORDER}
    fam_mean = {f: float(mean_abs[[c for c in fams[f] if c in mean_abs.index]].mean())
                for f in FAMILY_ORDER}
    total_shap = float(mean_abs.sum())
    shap_share = {f: v / total_shap for f, v in fam_sum.items()}

    # Per-row dominant family (which family has max |SHAP| that row).
    dom = []
    for f in FAMILY_ORDER:
        cols = [c for c in fams[f] if c in sh.columns]
        dom.append(sh[cols].abs().sum(axis=1).rename(f))
    dom_df = pd.concat(dom, axis=1)
    dominant = dom_df.idxmax(axis=1)
    dominant_share = pd.Series(dominant).value_counts(normalize=True)

    # --- 2. Leave-one-in (single-family RMSE) ---
    loo_in = {}
    for fam in FAMILY_ORDER:
        cols = [c for c in fams[fam]]
        m = _lgb(SEED).fit(tr[cols], ytr)
        p = m.predict(te[cols])
        loo_in[fam] = float(evaluate.regression_metrics(yte, p)["rmse"])
        print(f"  alone {fam:18s} rmse={loo_in[fam]:.3f}")

    # --- 3. Drop-family agreement: fresh LOO fits on LightGBM ---
    full_model = _lgb(SEED).fit(tr[all_cols], ytr)
    base_pred = full_model.predict(te[all_cols])
    full_rmse = float(evaluate.regression_metrics(yte, base_pred)["rmse"])
    agree_rows = []
    preds = pd.DataFrame({"operational_exposure_id": te["operational_exposure_id"],
                          "y_true": yte.values, "pred_full": base_pred})
    for fam in FAMILY_ORDER:
        keep = [c for c in all_cols if c not in fams[fam]]
        m = _lgb(SEED).fit(tr[keep], ytr)
        p = m.predict(te[keep])
        preds[f"pred_no_{fam}"] = p
        corr = float(np.corrcoef(base_pred, p)[0, 1])
        displacement = float(np.mean(np.abs(base_pred - p)))
        agree_rows.append({"removed": fam, "pearson": corr,
                           "mean_abs_displacement": displacement,
                           "loo_rmse": float(evaluate.regression_metrics(yte, p)["rmse"])})
        print(f"  drop {fam:18s} pearson={corr:.4f} disp={displacement:.3f} "
              f"rmse={np.sqrt(np.mean((yte-p)**2)):.3f}")

    preds.to_parquet(OUT_DIR / "drop_family_predictions.parquet", index=False)
    pd.DataFrame(agree_rows).to_csv(OUT_DIR / "drop_family_agreement.csv", index=False)
    pd.DataFrame([{"family": f, "shap_sum": fam_sum[f], "shap_mean": fam_mean[f],
                   "shap_share": shap_share[f],
                   "dominant_row_fraction": float(dominant_share.get(f, 0.0))}
                  for f in FAMILY_ORDER]).to_csv(OUT_DIR / "shap_family_attribution.csv", index=False)

    _report(fam_sum, fam_mean, shap_share, dominant_share, loo_in, agree_rows, full_rmse)
    print(f"-> {OUT_DIR}: shap_family_attribution.csv, drop_family_agreement.csv, "
          f"drop_family_predictions.parquet, family_attribution_report.md")


def _report(fam_sum, fam_mean, shap_share, dominant_share, loo_in, agree_rows, full_rmse) -> None:
    order = sorted(fam_sum, key=lambda f: -fam_sum[f])
    lines = [
        "# WS4 Family Attribution — LightGBM (v2.0, grouped test)",
        "",
        f"Full-set test RMSE = {full_rmse:.3f}. SHAP matrix from WS2 "
        f"(interpretability/experiment_0001).",
        "",
        "## SHAP family attribution",
        "",
        "| family | Σ\\|mean SHAP\\| | share % | per-feature mean | dominant-row % |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for f in order:
        lines.append(f"| {f} | {fam_sum[f]:.3f} | {shap_share[f]*100:.1f} | "
                     f"{fam_mean[f]:.3f} | {dominant_share.get(f,0)*100:.1f} |")
    lines += [
        "",
        "## Leave-one-in (single-family test RMSE, fresh LightGBM fits)",
        "",
        "| family | RMSE alone |",
        "| --- | ---: |",
    ]
    for f in sorted(loo_in, key=lambda x: loo_in[x]):
        lines.append(f"| {f} | {loo_in[f]:.3f} |")
    lines += [
        "",
        "## Drop-family agreement (full vs LOO predictions)",
        "",
        "| removed | Pearson | mean \\|Δpred\\| | LOO RMSE |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in sorted(agree_rows, key=lambda x: -x["mean_abs_displacement"]):
        lines.append(f"| {r['removed']} | {r['pearson']:.4f} | "
                     f"{r['mean_abs_displacement']:.3f} | {r['loo_rmse']:.3f} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- physics dominates SHAP sum but has 20 features; per-feature mean is the",
        "  size-fair comparison (geometry ≈ physics per feature).",
        "- Drop-family displacement measures how much each family moves predictions;",
        "  a family can be low-SHAP yet high-displacement if it acts on few rows.",
        "- exposure_v2 / physics_v2 SHAP is only driven by post-2023 rows (gated);",
        "  see feature_availability_report.md before reading too much into their",
        "  absolute magnitudes.",
    ]
    (OUT_DIR / "family_attribution_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
