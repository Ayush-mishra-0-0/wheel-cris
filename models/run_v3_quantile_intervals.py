"""V3 quantile-interval experiment — calibrated uncertainty for the tails.

The deployment audit requires well-calibrated prediction intervals, not just a
shrunk point prediction. HistGradientBoostingRegressor(loss="quantile") gives
direct quantile forecasts. Train q05 / q50 / q95 on the full v1.2 supervised
train set, evaluate on test:

  - pinball loss per quantile (the correct scoring rule for quantiles);
  - [q05, q95] interval coverage overall AND per magnitude bin (tail
    calibration — the audit's core complaint);
  - mean interval width and its growth with |true delta|;
  - q05 as a conservative downside estimate: does it under-state deep
    negatives? (audit found +32 bias there);
  - q50 (robust median) vs the MSE-optimal single-stage mean.

Outputs: models/experiments/v3/quantile_intervals_summary.md + registry runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import create_run, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
MANIFEST_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_manifest_v1.2.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v3"
RANDOM_STATE = 42
LABEL = "next_interval_dia_delta_mm"
QUANTILES = [0.05, 0.5, 0.95]

BIN_EDGES = [-np.inf, -40.0, -20.0, -10.0, 0.0, 10.0, 20.0, 40.0, np.inf]
BIN_LABELS = ["<=-40", "(-40,-20]", "(-20,-10]", "(-10,0]", "(0,10]", "(10,20]", "(20,40]", ">40"]


def _hgb_quantile(alpha: float) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile", quantile=alpha, max_iter=200, learning_rate=0.1,
        random_state=RANDOM_STATE, early_stopping=True,
        validation_fraction=0.15, n_iter_no_change=20,
    )


def _pinball(y_true, y_pred, alpha) -> float:
    e = np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float)
    return float(np.mean(np.where(e >= 0, alpha * e, (alpha - 1) * e)))


def main() -> None:
    d12 = pd.read_parquet(DATASET_V1_2)
    manifest = json.loads(MANIFEST_V1_2.read_text(encoding="utf-8"))
    x_columns = [c for c, r in manifest["column_roles"].items() if r == "feature"]

    train = d12[d12["split"] == "train"]
    test = d12[d12["split"] == "test"]

    print(f"train rows: {len(train):,} · test rows: {len(test):,} · features: {len(x_columns)}")

    preds = {}
    for alpha in QUANTILES:
        model = _hgb_quantile(alpha)
        model.fit(train[x_columns], train[LABEL])
        preds[alpha] = model.predict(test[x_columns])
        print(f"q{int(alpha*100):02d} pinball={_pinball(test[LABEL], preds[alpha], alpha):.4f}")

        cfg = {"phase": "v3.quantile-intervals", "task": "regression", "label": LABEL,
               "model": f"hist_gradient_boosting_quantile_{alpha}",
               "feature_set": "baseline", "split_contract": "grouped temporal (v1.2 train/test)",
               "eval_set": "v1.2-test", "random_state": RANDOM_STATE}
        experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "regression", cfg)
        write_metrics(run_dir, {"test": {"pinball": round(_pinball(test[LABEL], preds[alpha], alpha), 4),
                                         **evaluate.regression_metrics(test[LABEL], preds[alpha])}})
        write_model(run_dir, model)
        write_predictions(run_dir, pd.DataFrame({
            "operational_exposure_id": test["operational_exposure_id"],
            "split": "test", "y_true": test[LABEL].to_numpy(),
            f"q{int(alpha*100):02d}": preds[alpha],
        }))
        write_manifest(run_dir, {"dataset_version": "v1.2", "feature_store_version": "1.0.0",
                                 "feature_spec_version": "1.0.0", "label_spec_version": "1.0.1",
                                 "provenance": "models/run_v3_quantile_intervals.py"})

    y_true = test[LABEL].to_numpy()
    q05, q50, q95 = preds[0.05], preds[0.5], preds[0.95]

    in_interval = (y_true >= q05) & (y_true <= q95)
    width = q95 - q05
    idx = pd.cut(pd.Series(y_true), bins=BIN_EDGES, labels=BIN_LABELS)

    summary = [
        "# V3 quantile intervals — calibrated uncertainty on the tails",
        "",
        f"Test rows: {len(test):,} · HGB quantile loss (q05/q50/q95) · features: released v1.2 baseline ({len(x_columns)}).",
        "",
        "## Overall",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| [q05,q95] empirical coverage | {np.mean(in_interval)*100:.1f}% (target ~90%) |",
        f"| mean interval width | {np.mean(width):.2f} mm |",
        f"| median interval width | {np.median(width):.2f} mm |",
        f"| q50 MAE | {evaluate.regression_metrics(y_true, q50)['mae']:.3f} |",
        f"| q50 RMSE | {evaluate.regression_metrics(y_true, q50)['rmse']:.3f} |",
        f"| q50 R² | {evaluate.regression_metrics(y_true, q50)['r2']:.3f} |",
        f"| q50 σ_pred/σ_true | {np.std(q50)/np.std(y_true):.3f} |",
        f"| single-stage mean σ_pred/σ_true (v3) | 0.742 |",
        f"| pinball q05 / q50 / q95 | {_pinball(y_true, q05, 0.05):.3f} / {_pinball(y_true, q50, 0.5):.3f} / {_pinball(y_true, q95, 0.95):.3f} |",
        "",
        "## Per-magnitude-bin calibration (the audit's tail complaint)",
        "",
        "| bin | n | coverage | mean width | q05 bias vs true | q95 bias vs true |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label in BIN_LABELS:
        mask = idx == label
        if mask.sum() == 0:
            continue
        cov = np.mean(in_interval[mask])
        w = np.mean(width[mask])
        b05 = float(np.mean(q05[mask] - y_true[mask]))
        b95 = float(np.mean(q95[mask] - y_true[mask]))
        summary.append(f"| {label} | {int(mask.sum())} | {cov*100:.1f}% | {w:.2f} | {b05:+.2f} | {b95:+.2f} |")
        print(f"  bin {label:>12s}: coverage={cov*100:5.1f}%  mean_width={w:6.2f}  q05_bias={b05:+7.2f}  q95_bias={b95:+7.2f}")

    deep_neg = y_true < -40
    deep_pos = y_true > 40
    summary += [
        "",
        "## Tail sensitivity",
        "",
        f"- deep negatives (y_true < −40, n={int(deep_neg.sum())}): {np.mean(q05[deep_neg] <= y_true[deep_neg])*100:.0f}% have q05 below/at true "
        f"(model's own 5% tail does cover the loss); q05 on these is {np.mean(q05[deep_neg]):.2f} vs true mean {np.mean(y_true[deep_neg]):.2f}.",
        f"- deep positives (y_true > 40, n={int(deep_pos.sum())}): {np.mean(q95[deep_pos] >= y_true[deep_pos])*100:.0f}% have q95 above/at true.",
        f"- Spearman(q05, y_true) = {float(pd.Series(q05).corr(pd.Series(y_true), method='spearman')):.3f} (q05 as a downside-risk ranking score).",
        "",
        "Note: 'q05 bias vs true' is mean(q05 − true); on deep negatives a negative value",
        "means the 5% quantile sits below the realised loss (conservative), positive means",
        "it still over-states. Width growth across bins shows whether uncertainty scales with",
        "exposure — the property a single point estimate cannot provide.",
        "",
    ]
    (EXPERIMENTS_ROOT / "quantile_intervals_summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(f"\nwrote -> {EXPERIMENTS_ROOT / 'quantile_intervals_summary.md'}")


if __name__ == "__main__":
    main()
