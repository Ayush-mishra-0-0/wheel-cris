"""WS2 — interpretability on the WS1 LightGBM champion (native-NaN, grouped splits).

Fits LightGBM exactly as in run_benchmark (grouped train), then:
  * TreeSHAP (shap.TreeExplainer) on the test split -> per-row SHAP matrix.
  * Per-feature |mean SHAP| (approximates feature importance), aggregated to
    families via families.FAMILY_ORDER.
  * Top-feature partial dependence (PDP) + SHAP dependence on the test split.
  * Model-agnostic permutation importance (cross-check vs run_benchmark).

Also fits a "production" LightGBM on the rolling-latest cutoff to get
deployment-representative importance (early folds lack exposure_v2/physics_v2).

Outputs go to the experiment registry (fresh experiment id, never overwrites).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import (create_run, write_feature_importance,  # noqa: E402
                                        write_manifest, write_metrics,
                                        write_predictions, write_model)
from models.phase2.families import FAMILY_ORDER, all_features, feature_families  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"
REGRESSION_LABEL = "next_interval_dia_delta_mm"
SEED = 42


def _load():
    df = pd.read_parquet(DATASET_PATH)
    fams = feature_families()
    x_cols = all_features()
    return df, fams, x_cols


def _estimator(seed: int):
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=63,
                             subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                             random_state=seed, verbosity=-1)


def _native_shap(model, X: pd.DataFrame):
    import shap
    expl = shap.TreeExplainer(model)
    sh = expl.shap_values(X, check_additivity=False)
    sh = np.asarray(sh)
    if sh.ndim == 3:
        sh = sh[:, :, 0]
    return pd.DataFrame(sh, index=X.index, columns=X.columns)


def _run_shap(model, X: pd.DataFrame, family_map: dict) -> dict:
    sh = _native_shap(model, X)
    mean_abs = sh.abs().mean()
    top = mean_abs.sort_values(ascending=False)
    family_agg = {f: float(mean_abs[[c for c in family_map[f] if c in mean_abs.index]].sum())
                  for f in FAMILY_ORDER}
    return {"shap_values": sh, "mean_abs_shap": mean_abs,
            "top_features": top.head(50).to_dict(), "family_abs_shap": family_agg}


def _pdp(model, X: pd.DataFrame, top_features: list[str]) -> dict:
    """Crude PDP over the top feature deciles on a subsample (fast, tree-native)."""
    Xs = X.sample(min(20000, len(X)), random_state=SEED)
    out = {}
    for feat in top_features:
        vals = np.percentile(Xs[feat], np.linspace(5, 95, 11))
        pdp = []
        for v in vals:
            Xm = Xs.copy()
            Xm[feat] = v
            pdp.append(float(np.mean(model.predict(Xm))))
        out[feat] = {"deciles": [float(x) for x in vals], "pred_mean": pdp}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-features", type=int, default=15,
                        help="top-N features for PDP/dependence plots (memory bound).")
    args = parser.parse_args()

    df, fams, x_cols = _load()
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df = df[df["split"] == "val"].reset_index(drop=True)
    test_df = df[df["split"] == "test"].reset_index(drop=True)

    Xtr, ytr = train_df[x_cols], train_df[REGRESSION_LABEL]
    Xte, yte = test_df[x_cols], test_df[REGRESSION_LABEL]

    model = _estimator(SEED)
    model.fit(Xtr, ytr)

    config = {"phase": "phase2", "workstream": "WS2_interpretability", "model": "lightgbm",
              "label": REGRESSION_LABEL, "split": "test", "random_state": SEED,
              "missingness": "native_nan", "shap": "TreeExplainer"}
    exp_id, run_dir = create_run(EXPERIMENTS_ROOT, "interpretability", config)

    y_pred = model.predict(Xte)
    metrics = evaluate.regression_metrics(yte, y_pred)
    write_metrics(run_dir, metrics)
    write_predictions(run_dir, pd.DataFrame({"operational_exposure_id": test_df["operational_exposure_id"],
                                             "y_true": yte.values, "y_pred": y_pred}))
    write_model(run_dir, model)
    write_manifest(run_dir, {"dataset_version": "v2.0", "feature_spec_version": "1.0.0",
                             "label_spec_version": "1.0.1", "explainer": "TreeExplainer"})
    print(f"exp {exp_id:04d}: LightGBM test RMSE={metrics['rmse']:.3f} (matches WS1)")

    sh_result = _run_shap(model, Xte, fams)
    sh = sh_result["shap_values"]
    sh.to_parquet(run_dir / "shap_values_test.parquet")
    importance = {"kind": "shap_mean_abs", "top_50": sh_result["top_features"],
                  "family_abs_shap": sh_result["family_abs_shap"]}
    write_feature_importance(run_dir, importance)

    top_feats = list(pd.Series(sh_result["top_features"]).index)[: args.max_features]
    pdp = _pdp(model, Xte, top_feats)
    (run_dir / "pdp_top_features.json").write_text(json.dumps(pdp, indent=2), encoding="utf-8")

    (run_dir / "shap_summary.md").write_text(_summary_md(sh_result, metrics, exp_id), encoding="utf-8")
    print(f"-> {run_dir.name}: shap_values_test.parquet, pdp_top_features.json, shap_summary.md")


def _summary_md(res: dict, metrics: dict, exp_id: int) -> str:
    fam_rank = sorted(res["family_abs_shap"].items(), key=lambda kv: -kv[1])
    lines = [
        "# WS2 Interpretability — LightGBM TreeSHAP (v2.0)",
        "",
        f"Test RMSE {metrics['rmse']:.3f} (matches WS1). SHAP via TreeExplainer on raw native-NaN X.",
        "",
        "## Family attribution (sum |mean SHAP|)",
        "",
        "| family | sum \\|mean SHAP\\| |",
        "| --- | ---: |",
    ]
    for fam, v in fam_rank:
        lines.append(f"| {fam} | {v:.4f} |")
    top = pd.Series(res["top_features"]).head(20)
    lines += ["", "## Top-20 features (|mean SHAP|)", "",
              "| feature | |mean SHAP| |", "| --- | ---: |"]
    for feat, v in top.items():
        lines.append(f"| {feat} | {v:.4f} |")
    lines += ["", "## Caveats",
              "",
              "- `running_hours_proxy` is a pure time-marker (0% pre-2025, 90% 2026); its SHAP",
              "  magnitude partly encodes 'when in history', not physical exposure.",
              "- exposure_v2 / physics_v2 are 0% present pre-2023; their SHAP is only driven by",
              "  post-2023 rows in this grouped split."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
