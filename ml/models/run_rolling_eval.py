"""Production-simulation (rolling temporal) evaluation — the "Problem B" protocol.

Grouped-wheelset split answers: "does the model generalise to wheels it has never
seen?" This protocol answers the OTHER question: "if CRIS deploys this model today,
how accurately does it predict the NEXT inspection for wheels that keep accumulating
history?" — exactly the RUL production flow.

At each cutoff date T:
  - TRAIN on every row whose next inspection already happened (next_interval_end <= T).
    This uses each wheel's ENTIRE past history (features are point-in-time safe: a row's
    features only use data up to its own interval_end < next_interval_end).
  - EVALUATE on rows with interval_end <= T < next_interval_end: wheels whose latest
    inspection happened at/before T and whose next inspection is still pending. Ground
    truth is known only retrospectively because the historical dataset extends past T.
    These are exactly the predictions a deployed model would issue "today" at T.

A wheel may appear in both train and eval (that is intended — it is the deployment
scenario). The eval rows' features never include the label horizon.

Outputs land in models/experiments/v1.0/rolling_eval/cutoff_YYYYMMDD/:
  - model.joblib / model_info.json   (the persisted "bin" artifact)
  - metrics.json                     (per task/label)
  - predictions.parquet              (row-level predictions for the eval set)
  - dataset_card.txt                 (how many train / eval rows)
plus rolling_metrics.csv / rolling_summary.md / rolling_trend.png across all cutoffs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import write_metrics, write_model, write_predictions  # noqa: E402

DATA_DIR = PROJECT_ROOT / "model_datasets" / "v1.0"
DATASET_PATH = DATA_DIR / "model_dataset_v1.0.parquet"
MANIFEST_PATH = DATA_DIR / "model_dataset_manifest_v1.0.json"
OUT_DIR = PROJECT_ROOT / "models" / "experiments" / "v1.0" / "rolling_eval"
RANDOM_STATE = 42

REGRESSION_LABEL = "next_interval_dia_delta_mm"
BINARY_LABELS = ["next_interval_turning_flag", "next_interval_large_loss_flag"]
SURVIVAL_LABEL = "time_to_next_turning_days"
SURVIVAL_CENSOR = "censored_flag"


def _load() -> tuple[pd.DataFrame, dict]:
    dataset = pd.read_parquet(DATASET_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text())
    return dataset, manifest


def _features(manifest: dict) -> list[str]:
    return [c for c, r in manifest["column_roles"].items() if r == "feature"]


def _cutoffs(dataset: pd.DataFrame, n: int = 8) -> list[pd.Timestamp]:
    """n evenly spaced cutoffs across the observed data range (safe margin at both ends)."""
    lo = dataset["next_interval_end_timestamp"].min()
    hi = dataset["next_interval_end_timestamp"].max()
    # Keep at least ~1 year of data before the first cutoff and after the last.
    span = (hi - lo).days
    start = lo + pd.Timedelta(days=int(span * 0.15))
    end = hi - pd.Timedelta(days=int(span * 0.10))
    return [start + pd.Timedelta(days=(end - start).days * i / (n - 1)) for i in range(n)]


def _split_at_cutoff(dataset: pd.DataFrame, features: list[str], cutoff: pd.Timestamp):
    """Returns (train_df, eval_df) for the given cutoff (see module docstring)."""
    next_end = dataset["next_interval_end_timestamp"]
    end = dataset["interval_end_timestamp"]
    train = dataset[next_end <= cutoff]
    eval_df = dataset[(end <= cutoff) & (cutoff < next_end)]
    return train, eval_df


def _train_eval(train_df: pd.DataFrame, eval_df: pd.DataFrame, features: list[str], cutoff: pd.Timestamp) -> dict:
    """Train HGB + logistic on train, evaluate on the production-simulation eval set."""
    results = {}
    # ---- Regression: diameter delta over next interval ----
    reg = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
                                        early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
    reg.fit(train_df[features], train_df[REGRESSION_LABEL])
    y_pred = reg.predict(eval_df[features])
    m = evaluate.regression_metrics(eval_df[REGRESSION_LABEL], y_pred)
    results["regression"] = {"label": REGRESSION_LABEL, "metrics": m, "model": reg, "kind": "hgb"}

    # ---- Binary: large loss + turning flag ----
    for label in BINARY_LABELS:
        cls = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
                                             early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
        cls.fit(train_df[features], train_df[label])
        y_prob = cls.predict_proba(eval_df[features])[:, 1]
        m = evaluate.binary_metrics(eval_df[label], y_prob, k=min(2000, len(eval_df)))
        results[label] = {"label": label, "metrics": m, "model": cls, "kind": "hgb"}

    # ---- Survival: time to next turning (train on uncensored rows only) ----
    observed_train = train_df[~train_df[SURVIVAL_CENSOR]]
    surv = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1, random_state=RANDOM_STATE,
                                         early_stopping=True, validation_fraction=0.15, n_iter_no_change=20)
    if len(observed_train) > 0:
        surv.fit(observed_train[features], observed_train[SURVIVAL_LABEL])
        risk = -surv.predict(eval_df[features])
    else:
        risk = np.full(len(eval_df), -1.0)
    event_eval = (~eval_df[SURVIVAL_CENSOR]).astype(int)
    m = evaluate.survival_metrics(eval_df[SURVIVAL_LABEL], event_eval, risk)
    results["survival"] = {"label": SURVIVAL_LABEL, "metrics": m, "model": surv, "kind": "hgb"}

    return results


def _summarize_row(cutoff: pd.Timestamp, split_key: str, n_train: int, n_eval: int, task: str, label: str, model: str, metrics: dict) -> dict:
    metric_key = {"regression": "rmse", "survival": "c_index"}.get(task)
    primary = metrics.get(metric_key) if metric_key else metrics.get("pr_auc")
    return {
        "cutoff": cutoff.date().isoformat(), "split_key": split_key,
        "n_train": n_train, "n_eval": n_eval, "task": task, "label": label, "model": model,
        "primary": primary, **{k: v for k, v in metrics.items() if k not in ("n",)},
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset, manifest = _load()
    features = _features(manifest)
    cutoffs = _cutoffs(dataset, n=8)

    all_rows = []
    # Dummy references computed once on the full supervised set (deployment-style reference)
    for cutoff in cutoffs:
        train_df, eval_df = _split_at_cutoff(dataset, features, cutoff)
        print(f"cutoff {cutoff.date()}: n_train={len(train_df)} n_eval={len(eval_df)}")
        results = _train_eval(train_df, eval_df, features, cutoff)

        run_dir = OUT_DIR / f"cutoff_{cutoff.date():%Y%m%d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        all_metrics = {}
        for task_key, res in results.items():
            all_metrics[task_key] = res["metrics"]
            write_model(run_dir, res["model"], model_format="joblib")
            model_path = run_dir / f"model_{task_key}.joblib"
            if run_dir.joinpath("model.joblib").exists():
                run_dir.joinpath("model.joblib").replace(model_path)
            task = "regression" if task_key == "regression" else ("survival" if task_key == "survival" else "binary")
            if task == "regression":
                cols = {"operational_exposure_id": eval_df["operational_exposure_id"], "y_true": eval_df[REGRESSION_LABEL], "y_pred": res["model"].predict(eval_df[features])}
            elif task == "binary":
                cols = {"operational_exposure_id": eval_df["operational_exposure_id"], "y_true": eval_df[task_key], "y_prob": res["model"].predict_proba(eval_df[features])[:, 1]}
            else:
                cols = {"operational_exposure_id": eval_df["operational_exposure_id"], "time_to_event": eval_df[SURVIVAL_LABEL], "censored": (~eval_df[SURVIVAL_CENSOR]).astype(int), "risk_score": -res["model"].predict(eval_df[features])}
            write_predictions(run_dir, pd.DataFrame(cols))
            run_dir.joinpath("predictions.parquet").replace(run_dir / f"predictions_{task_key}.parquet")
            row = _summarize_row(cutoff, "deployment_sim", len(train_df), len(eval_df), task, res["label"], res["kind"], res["metrics"])
            all_rows.append(row)
        write_metrics(run_dir, all_metrics)
        (run_dir / "model_info.json").write_text(json.dumps(
            {"model_format": "joblib",
             "artifacts": [f"model_{k}.joblib" for k in results.keys()]},
            indent=2) + "\n", encoding="utf-8")
        (run_dir / "dataset_card.txt").write_text(
            f"cutoff={cutoff.date().isoformat()}\nn_train={len(train_df)}\nn_eval={len(eval_df)}\n"
            f"features={len(features)}\nprotocol=rolling temporal production simulation\n",
            encoding="utf-8",
        )

    rolling = pd.DataFrame(all_rows)
    rolling.to_csv(OUT_DIR / "rolling_metrics.csv", index=False)

    # ---- Trend chart: primary metric over cutoffs ----
    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5))
    for ax, (task, metric_name, invert) in zip(axes, [
        ("regression", "rmse", True),
        ("binary", "pr_auc", False),
        ("survival", "c_index", False),
    ]):
        sub = rolling[rolling["task"] == task]
        if task == "binary":
            sub = sub[sub["label"] == "next_interval_large_loss_flag"]
        pivot = sub.pivot_table(index="cutoff", values=metric_name, aggfunc="first")
        pivot.sort_index().plot(ax=ax, marker="o", legend=False, color="#2b5c8f" if not invert else "#e6550d")
        ax.set_title(f"{task}: {metric_name} over time" + (" (lower=better)" if invert else " (higher=better)"))
        ax.set_xlabel("Cutoff (deployment date)")
        ax.set_ylabel(metric_name)
        ax.grid(True, alpha=0.3)
        for tick in ax.get_xticklabels():
            tick.set_rotation(30)
            tick.set_ha("right")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "rolling_trend.png", dpi=120)
    plt.show()

    # ---- Markdown summary ----
    lines = ["# Rolling Temporal (Production Simulation) Evaluation — v1.0", "",
             "Protocol: at each cutoff date T, train on all intervals whose next inspection "
             "already occurred (next_interval_end <= T) and evaluate on wheels whose next "
             "inspection is still pending (interval_end <= T < next_interval_end). This "
             "measures how the deployed system would actually perform, where each wheel "
             "accumulates more history over time.", ""]
    for task_name in ["regression", "binary", "survival"]:
        sub = rolling[rolling["task"] == task_name]
        lines.append(f"## {task_name}")
        lines.append("")
        lines.append("| cutoff | n_train | n_eval | model | primary |")
        lines.append("| --- | --- | --- | --- | --- |")
        for _, r in sub.iterrows():
            primary_key = {"regression": "rmse", "binary": "pr_auc", "survival": "c_index"}[task_name]
            val = r.get(primary_key)
            lines.append(f"| {r['cutoff']} | {r['n_train']} | {r['n_eval']} | {r['model']} | {val} |")
        lines.append("")
    (OUT_DIR / "rolling_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"rolling evaluation written -> {OUT_DIR}")
    print(rolling[["cutoff", "task", "label", "primary"]].to_string(index=False))


if __name__ == "__main__":
    main()
