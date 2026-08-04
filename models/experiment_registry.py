"""Experiment registry — every run produces a versioned, self-describing directory.

experiments/<task>/experiment_XXXX/
    config.json              (model, hyperparameters, label, split contract)
    metrics.json             (all metrics for val + test)
    predictions.parquet      (row-level: ids, split, y_true, y_pred / y_prob, risk)
    feature_importance.json  (importance/coefficients where the model exposes them)
    manifest.json            (provenance: dataset version, feature/label spec, code sha)

Never overwrite: a fresh experiment id is allocated per run.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd


def _safe(value) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", str(value))


def allocate_experiment_id(root: Path, task: str) -> int:
    task_dir = root / task
    task_dir.mkdir(parents=True, exist_ok=True)
    existing = [int(p.name.removeprefix("experiment_")) for p in task_dir.glob("experiment_*")]
    return (max(existing) + 1) if existing else 1


def create_run(root: Path, task: str, config: dict) -> tuple[int, Path]:
    experiment_id = allocate_experiment_id(root, task)
    run_dir = root / task / f"experiment_{experiment_id:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return experiment_id, run_dir


def write_metrics(run_dir: Path, metrics: dict) -> None:
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8")


def write_predictions(run_dir: Path, predictions: pd.DataFrame) -> None:
    predictions.to_parquet(run_dir / "predictions.parquet", index=False)


def write_feature_importance(run_dir: Path, importance: dict) -> None:
    (run_dir / "feature_importance.json").write_text(json.dumps(importance, indent=2, default=str) + "\n", encoding="utf-8")


def write_manifest(run_dir: Path, manifest: dict) -> None:
    manifest.setdefault("generated_at_utc", datetime.now(timezone.utc).isoformat())
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")


def write_model(run_dir: Path, model, model_format: str = "joblib") -> None:
    """Persist the fitted estimator so the experiment is reproducible/deployable.

    Default is joblib (a binary — the "bin file" people expect after training).
    A pickle fallback is provided in case an estimator is not joblib-serializable.
    """
    if model is None:
        return
    if model_format == "joblib":
        joblib.dump(model, run_dir / "model.joblib")
    else:
        import pickle
        with open(run_dir / "model.pkl", "wb") as fh:
            pickle.dump(model, fh)
    # Record which artifact exists for easy discovery.
    info_path = run_dir / "model_info.json"
    existing = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    existing["model_format"] = model_format
    existing["artifact"] = "model.joblib" if model_format == "joblib" else "model.pkl"
    info_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
