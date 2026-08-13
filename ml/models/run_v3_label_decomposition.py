"""V3 label-decomposition experiment — break the regression-to-mean plateau.

The v1.2 regression label `next_interval_dia_delta_mm` is a MIXTURE of two
physically different events: ordinary wear (small, mostly negative) and
large-loss intervals (diameter/root drop beyond heuristic thresholds). A
single-stage conditional-mean regressor over that mixture must shrink to the
middle -> range compression + tail bias (sigma_pred/sigma_true ~0.74, +32 bias
on deep negatives). This experiment tests the stage-1/stage-2 decomposition:

  stage 1 (detection)  : P(large_loss in next interval)  [binary]
  stage 2a (wear)      : E[delta | no large loss]        [regression, clean]
  stage 2b (loss)      : E[delta | large loss]           [regression, loss]
  combined             : E[delta] = P*stage2b + (1-P)*stage2a

Reference is a single-stage HGB on the same rows/features (the v1.2 champion
config). Diagnostics follow the deployment audit: overall MAE/RMSE/R2/Spearman,
sigma compression ratio, coverage within +-5/+-10, and per-magnitude-bin
conditional bias. Two feature sets: released v1.2 baseline, and the same plus
the 3 experimental RTIS distance columns.

Outputs: models/experiments/v3/label_decomposition/ summary + registry runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
DISTANCE_X = PROJECT_ROOT / "model_datasets" / "v1.2" / "distance_experimental.parquet"
MANIFEST_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_manifest_v1.2.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v3"
RANDOM_STATE = 42
LABEL = "next_interval_dia_delta_mm"
LOSS_LABEL = "next_interval_large_loss_flag"
DISTANCE_FEATURES = [
    "interval_distance_km_experimental",
    "rtis_distance_coverage_days",
    "rtis_distance_coverage_pct",
]

BIN_EDGES = [-np.inf, -40.0, -20.0, -10.0, 0.0, 10.0, 20.0, 40.0, np.inf]
BIN_LABELS = ["<=-40", "(-40,-20]", "(-20,-10]", "(-10,0]", "(0,10]", "(10,20]", "(20,40]", ">40"]


def _hgb_reg() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=20,
    )


def _hgb_clf() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=20,
    )


def _importance(model, x_columns, X, y, scoring="neg_mean_squared_error"):
    try:
        from sklearn.inspection import permutation_importance
        perm = permutation_importance(model, X, y, n_repeats=2, random_state=RANDOM_STATE,
                                      scoring=scoring, n_jobs=-1)
        rank = pd.Series(perm.importances_mean, index=x_columns).sort_values(ascending=False)
        return {"kind": "permutation_importance", "scorer": scoring, "top_30": rank.head(30).to_dict()}
    except Exception:
        return {"kind": "unavailable"}


def _tail_diagnostics(y_true, y_pred) -> dict:
    """Deployment-audit metrics: overall + per-magnitude-bin conditional bias."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[valid], y_pred[valid]
    err = y_true - y_pred
    abs_err = np.abs(err)
    n = len(y_true)
    out = {
        "n": int(n),
        "mae": float(np.mean(abs_err)),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "r2": float(1.0 - np.sum(err ** 2) / np.sum((y_true - np.mean(y_true)) ** 2)) if np.sum((y_true - np.mean(y_true)) ** 2) > 0 else np.nan,
        "sigma_pred": float(np.std(y_pred)),
        "sigma_true": float(np.std(y_true)),
        "sigma_ratio": float(np.std(y_pred) / np.std(y_true)) if np.std(y_true) > 0 else np.nan,
        "pct_within_5": float(np.mean(abs_err <= 5.0)),
        "pct_within_10": float(np.mean(abs_err <= 10.0)),
        "p95_abs_err": float(np.quantile(abs_err, 0.95)),
        "max_abs_err": float(np.max(abs_err)),
        "bins": {},
    }
    idx = pd.cut(pd.Series(y_true), bins=BIN_EDGES, labels=BIN_LABELS)
    for label in BIN_LABELS:
        mask = idx == label
        if mask.sum() == 0:
            continue
        e = err[mask]
        out["bins"][label] = {
            "n": int(mask.sum()),
            "bias_mean_pred_minus_true": float(np.mean(e)),
            "mae": float(np.mean(np.abs(e))),
        }
    return out


def _diagnostics_rows(diagnostics: dict) -> list[dict]:
    rows = []
    for label, d in diagnostics["bins"].items():
        rows.append({"bin": label, **{k: d[k] for k in ("n", "bias_mean_pred_minus_true", "mae")}})
    return rows


def main() -> None:
    d12 = pd.read_parquet(DATASET_V1_2)
    dist = pd.read_parquet(DISTANCE_X)
    manifest = json.loads(MANIFEST_V1_2.read_text(encoding="utf-8"))
    base_features = [c for c, r in manifest["column_roles"].items() if r == "feature"]

    dataset = d12.merge(dist, on="operational_exposure_id", how="left", validate="one_to_one")
    assert len(dataset) == len(d12), "distance join must be one-to-one"
    dataset = dataset.dropna(subset=[LOSS_LABEL])

    train = dataset[dataset["split"] == "train"]
    val = dataset[dataset["split"] == "val"]
    test = dataset[dataset["split"] == "test"]

    feature_sets = [
        ("baseline", base_features),
        ("baseline_plus_distance", base_features + DISTANCE_FEATURES),
    ]

    summary = [
        "# V3 label-decomposition — stage-1 detection + stage-2 wear regression",
        "",
        f"Eval rows (v1.2 test, sentinel-free): {len(test):,}. Train rows: {len(train):,}.",
        f"Large-loss prevalence: train {train[LOSS_LABEL].mean():.4f} · val {val[LOSS_LABEL].mean():.4f} · test {test[LOSS_LABEL].mean():.4f}",
        "",
        "Model per feature set: stage-1 HGB classifier on `next_interval_large_loss_flag`;",
        "stage-2a HGB on clean intervals (`large_loss_flag==0`); stage-2b HGB on loss",
        "intervals; combined = P*loss_pred + (1-P)*clean_pred. Single-stage HGB on all",
        "intervals is the champion reference. All on the same rows.",
        "",
    ]

    for set_name, x_cols in feature_sets:
        print(f"\n=== feature set: {set_name} ({len(x_cols)} features) ===")

        # ---- stage 1: detection ----
        clf = _hgb_clf()
        clf.fit(train[x_cols], train[LOSS_LABEL])
        p_val = clf.predict_proba(val[x_cols])[:, 1]
        p_test = clf.predict_proba(test[x_cols])[:, 1]
        bin_val = evaluate.binary_metrics(val[LOSS_LABEL], p_val)
        bin_test = evaluate.binary_metrics(test[LOSS_LABEL], p_test)
        print(f"[stage1 detection] val PR-AUC={bin_val['pr_auc']} ROC-AUC={bin_val['roc_auc']} | "
              f"test PR-AUC={bin_test['pr_auc']} ROC-AUC={bin_test['roc_auc']} P@1000={bin_test['precision_at_k']}")

        # ---- stage 2a / 2b: conditional regressions ----
        tr_clean = train[train[LOSS_LABEL] == 0]
        tr_loss = train[train[LOSS_LABEL] == 1]
        reg_clean = _hgb_reg().fit(tr_clean[x_cols], tr_clean[LABEL])
        reg_loss = _hgb_reg().fit(tr_loss[x_cols], tr_loss[LABEL])
        y_clean_all = reg_clean.predict(test[x_cols])
        y_loss_all = reg_loss.predict(test[x_cols])
        y_clean_test = reg_clean.predict(test[test[LOSS_LABEL] == 0][x_cols])
        print(f"[stage2a clean] n_train={len(tr_clean):,} | [stage2b loss] n_train={len(tr_loss):,}")

        # ---- single-stage reference ----
        reg_single = _hgb_reg().fit(train[x_cols], train[LABEL])
        y_single = reg_single.predict(test[x_cols])
        diag_single = _tail_diagnostics(test[LABEL], y_single)
        m_single = evaluate.regression_metrics(test[LABEL], y_single)
        print(f"[single-stage]  test MAE={m_single['mae']} RMSE={m_single['rmse']} R2={m_single['r2']} "
              f"sigma_ratio={diag_single['sigma_ratio']:.3f}")

        # ---- combined expectation ----
        y_combined = p_test * y_loss_all + (1.0 - p_test) * y_clean_all
        diag_combined = _tail_diagnostics(test[LABEL], y_combined)
        m_combined = evaluate.regression_metrics(test[LABEL], y_combined)
        print(f"[combined]      test MAE={m_combined['mae']} RMSE={m_combined['rmse']} R2={m_combined['r2']} "
              f"sigma_ratio={diag_combined['sigma_ratio']:.3f}")

        # ---- stage-2a only on clean subset (what a clean-regression alone buys) ----
        clean_mask = test[LOSS_LABEL] == 0
        y_clean_only = reg_clean.predict(test[clean_mask][x_cols])
        diag_clean = _tail_diagnostics(test.loc[clean_mask, LABEL], y_clean_only)

        # ---- persist runs ----
        for tag, task, cfg_extra, model, yp, diag, metrics in [
            ("stage1_detection", "binary", {"stage": "stage1_detection", "label": LOSS_LABEL, "model": "hist_gradient_boosting"}, clf, None, None, bin_test),
            ("stage2a_clean", "regression", {"stage": "stage2a_clean", "label": LABEL, "model": "hist_gradient_boosting"}, reg_clean, None, diag_clean, evaluate.regression_metrics(test.loc[clean_mask, LABEL], y_clean_only)),
            ("stage2b_loss", "regression", {"stage": "stage2b_loss", "label": LABEL, "model": "hist_gradient_boosting"}, reg_loss, None, None, evaluate.regression_metrics(test[test[LOSS_LABEL] == 1][LABEL], reg_loss.predict(test[test[LOSS_LABEL] == 1][x_cols]))),
            ("single_stage", "regression", {"stage": "single_stage_reference", "label": LABEL, "model": "hist_gradient_boosting"}, reg_single, y_single, diag_single, m_single),
            ("combined", "regression", {"stage": "combined_expectation", "label": LABEL, "model": "hist_gradient_boosting"}, None, y_combined, diag_combined, m_combined),
        ]:
            config = {"phase": "v3.label-decomposition", "task": "regression" if task == "regression" else "binary",
                      "feature_set": set_name, "split_contract": "grouped temporal (v1.2 train/val/test, identical rows)",
                      "eval_set": "v1.2-test", "random_state": RANDOM_STATE, **cfg_extra}
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, task, config)
            write_metrics(run_dir, {"test": metrics})
            write_manifest(run_dir, {"dataset_version": "v1.2", "feature_store_version": "1.0.0",
                                     "feature_spec_version": "1.0.0", "label_spec_version": "1.0.1",
                                     "experimental_features": DISTANCE_FEATURES if set_name == "baseline_plus_distance" else [],
                                     "provenance": "models/run_v3_label_decomposition.py"})
            if model is not None:
                write_model(run_dir, model)
            if yp is not None:
                write_predictions(run_dir, pd.DataFrame({
                    "operational_exposure_id": test["operational_exposure_id"],
                    "split": "test", "y_true": test[LABEL].to_numpy(), "y_pred": yp,
                }))
            if diag is not None:
                (run_dir / "tail_diagnostics.json").write_text(json.dumps(diag, indent=2) + "\n", encoding="utf-8")
        # stage-1 importance on baseline set only (drivers of detection)
        if set_name == "baseline":
            write_feature_importance(run_dir, _importance(clf, x_cols, test[x_cols], test[LOSS_LABEL], scoring="neg_log_loss"))

        # ---- summary tables ----
        summary.append(f"## {set_name}")
        summary.append("")
        summary.append("| component | MAE | RMSE | R² | Spearman | σ_pred/σ_true | ≤±5 | ≤±10 | p95 |")
        summary.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for tag, diag, m in [
            ("single-stage", diag_single, m_single),
            ("combined", diag_combined, m_combined),
            ("stage-2a (clean only)", diag_clean, evaluate.regression_metrics(test.loc[clean_mask, LABEL], y_clean_only)),
        ]:
            summary.append(f"| {tag} | {m['mae']:.3f} | {m['rmse']:.3f} | {m['r2']:.3f} | {m['spearman']:.3f} | "
                           f"{diag['sigma_ratio']:.3f} | {diag['pct_within_5']*100:.1f}% | {diag['pct_within_10']*100:.1f}% | {diag['p95_abs_err']:.1f} |")
        summary.append("")
        summary.append("| stage-1 detection (test) | PR-AUC | ROC-AUC | precision@1000 | ECE | positive_rate |")
        summary.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        summary.append(f"| {set_name} | {bin_test['pr_auc']:.4f} | {bin_test['roc_auc']:.4f} | "
                       f"{bin_test['precision_at_k']:.4f} | {bin_test['ece']:.4f} | {bin_test['positive_rate']:.4f} |")
        summary.append("")
        summary.append("### Conditional bias by magnitude bin (pred − true; positive = over-predict / under-state loss)")
        summary.append("")
        summary.append("| bin | n | single bias | single MAE | combined bias | combined MAE |")
        summary.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        single_bins = {r["bin"]: r for r in _diagnostics_rows(diag_single)}
        comb_bins = {r["bin"]: r for r in _diagnostics_rows(diag_combined)}
        for label in BIN_LABELS:
            s, c = single_bins.get(label), comb_bins.get(label)
            if s is None and c is None:
                continue
            s_n = s["n"] if s else 0
            s_b = f"{s['bias_mean_pred_minus_true']:+.2f}" if s else "-"
            s_m = f"{s['mae']:.2f}" if s else "-"
            c_b = f"{c['bias_mean_pred_minus_true']:+.2f}" if c else "-"
            c_m = f"{c['mae']:.2f}" if c else "-"
            summary.append(f"| {label} | {s_n} | {s_b} | {s_m} | {c_b} | {c_m} |")
        summary.append("")

    (EXPERIMENTS_ROOT / "label_decomposition_summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"\nwrote -> {EXPERIMENTS_ROOT / 'label_decomposition_summary.md'}")


if __name__ == "__main__":
    main()
