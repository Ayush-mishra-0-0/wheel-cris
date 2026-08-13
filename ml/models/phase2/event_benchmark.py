"""Part 2 — Event-label benchmark on v2.0 features (grouped splits).

Labels: next_interval_turning_flag (rare, 1.1%) and next_interval_large_loss_flag.
Model: LightGBM (native-NaN, matching the WS1 champion setup). Metrics per the
evaluation contract: PR-AUC (primary, class imbalance) + ROC-AUC + F1 + precision@k.

The large-loss label uses a -2.0mm heuristic threshold that sits BELOW the ~3mm
measurement noise floor (label_audit) — expected to fire on noise; we quantify it.

Outputs: registry experiment + event_benchmark_report.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import (create_run, write_manifest, write_metrics,  # noqa: E402
                                        write_predictions)
from models.phase2.families import all_features  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"
SEED = 42
LABELS = ["next_interval_turning_flag", "next_interval_large_loss_flag"]


def main() -> None:
    df = pd.read_parquet(DATASET_PATH)
    x_cols = all_features()
    rows = []

    for label in LABELS:
        tr = df[df["split"] == "train"].reset_index(drop=True)
        te = df[df["split"] == "test"].reset_index(drop=True)
        Xtr, ytr = tr[x_cols], tr[label].astype(int)
        Xte, yte = te[x_cols], te[label].astype(int)

        import lightgbm as lgb
        model = lgb.LGBMClassifier(n_estimators=500, learning_rate=0.05, num_leaves=63,
                                   subsample=0.8, colsample_bytree=0.8,
                                   scale_pos_weight=None, n_jobs=-1,
                                   random_state=SEED, verbosity=-1)
        model.fit(Xtr, ytr)
        y_prob = model.predict_proba(Xte)[:, 1]
        metrics = evaluate.binary_metrics(yte, y_prob)

        config = {"phase": "phase2", "part": "2_event_labels", "label": label,
                  "model": "lightgbm", "split": "test", "random_state": SEED,
                  "missingness": "native_nan"}
        exp_id, run_dir = create_run(EXPERIMENTS_ROOT, "event_benchmark", config)
        write_metrics(run_dir, metrics)
        write_predictions(run_dir, pd.DataFrame({"operational_exposure_id": te["operational_exposure_id"],
                                                 "y_true": yte.values, "y_prob": y_prob}))
        write_manifest(run_dir, {"dataset_version": "v2.0", "feature_spec_version": "1.0.0",
                                 "label_spec_version": "1.0.1"})
        rows.append({"label": label, "experiment": f"experiment_{exp_id:04d}", **metrics})
        print(f"  {label:40s} PR-AUC={metrics['pr_auc']:.4f} ROC-AUC={metrics['roc_auc']:.4f} "
              f"pos_rate={metrics['positive_rate']:.4f}")

    out = EXPERIMENTS_ROOT / "event_benchmark_report.md"
    lines = [
        "# Part 2 — Event-label benchmark (v2.0, grouped test)",
        "",
        "| label | n | pos rate | PR-AUC | ROC-AUC | F1@best | prec@1000 | Brier | ECE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(f"| {r['label']} | {r['n']} | {r['positive_rate']:.4f} | "
                     f"{r['pr_auc']:.4f} | {r['roc_auc']:.4f} | {r['f1_at_best']:.3f} | "
                     f"{r['precision_at_k']:.4f} | {r['brier']:.4f} | {r['ece']:.4f} |")
    lines += [
        "",
        "## Notes",
        "",
        "- PR-AUC is primary (rare events); random baseline = positive rate.",
        "- large_loss threshold (-2.0mm) < 3mm noise floor => label likely noise-driven.",
        "- turning_flag (1.1%) is the crisp maintenance event; ROC-AUC above ~0.75 with",
        "  1.1% prevalence is operationally meaningful.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
