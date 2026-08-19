"""Proper survival modelling for time_to_next_turning_days (review item 2).

Fixes the v1.2-era evalu BBB: the previous "survival" entry trained an HGB
regressor on the ~9% uncensored rows only and called that a baseline — a
survivorship-biased design. This script builds a real right-censored setup:

  - censoring time = per-wheelset observation end: days from the row's
    interval_end_timestamp to that wheelset's LAST measurement on record
    (verified per-wheelset end, not a global nominal dataset end — the
    phase3 target-evaluation contract requires exactly this).
  - uncensored rows keep time_to_next_turning_days and event=1; censored
    rows get follow-up time = (last measurement − interval_end) and event=0.
  - learners: CoxPH, RandomSurvivalForest, GradientBoostingSurvivalAnalysis
    (scikit-survival) trained on the FULL train set (all 144k rows, 91%
    censored); reference = median-time dummy.
  - metric: Harrell C-index via sksurv.metrics.concordance_index_censored.

Outputs: models/experiments/v1.2_survival/survival/ + comparison summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from models.experiment_registry import create_run, write_feature_importance, write_manifest, write_metrics, write_model, write_predictions  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
MEASUREMENTS_PATH = PROJECT_ROOT / "data" / "silver" / "wheel_measurements.parquet"
MANIFEST_PATH = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_manifest_v1.2.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v1.2_survival"
RANDOM_STATE = 42

SURVIVAL_LABEL = "time_to_next_turning_days"
SURVIVAL_CENSOR = "censored_flag"


def _last_measurement_times() -> pd.Series:
    meas = pd.read_parquet(
        MEASUREMENTS_PATH, columns=["wsmEquipmentId", "wsmUpdatedOn"]
    ).dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"])
    meas["t"] = pd.to_datetime(meas["wsmUpdatedOn"])
    last = meas.groupby("wsmEquipmentId")["t"].max()
    last = last.rename("last_measurement_time")
    return last


def _feature_list() -> list[str]:
    return [c for c, r in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["column_roles"].items() if r == "feature"]


def _structured(dataset: pd.DataFrame) -> pd.DataFrame:
    """Build event+time columns and a structured sksurv-compatible array."""
    last = _last_measurement_times()
    ds = dataset.merge(last, left_on="wheelset_equipment_id", right_index=True, how="left")
    end_ts = pd.to_datetime(ds["interval_end_timestamp"])
    followup = (pd.to_datetime(ds["last_measurement_time"]) - end_ts).dt.days

    event_time = ds[SURVIVAL_LABEL].copy()
    censored = ds[SURVIVAL_CENSOR].astype(int) == 1
    event = (~censored).astype(int)

    # censored rows get the verified per-wheelset observation end as their follow-up
    time = np.where(event == 1, event_time, followup.to_numpy())
    time = pd.Series(time).astype(float)
    valid = time.notna() & (time > 0) & (event_time.notna() | censored)
    out = ds.loc[valid].copy()
    out["time_to_event"] = time.loc[valid].to_numpy()
    out["event_flag"] = event.loc[valid].to_numpy()
    return out


def _lifelines_array(time, event) -> np.ndarray:
    dtype = [("event", bool), ("time", float)]
    arr = np.empty(len(time), dtype=dtype)
    arr["event"] = event.astype(bool)
    arr["time"] = np.asarray(time, dtype=float)
    return arr


def main() -> None:
    dataset = pd.read_parquet(DATASET_PATH)
    features = _feature_list()
    ds = _structured(dataset)

    X = ds[features].to_numpy()
    y = _lifelines_array(ds["time_to_event"], ds["event_flag"])
    dummies = {
        "train": ds["split"] == "train",
        "val": ds["split"] == "val",
        "test": ds["split"] == "test",
    }

    from sklearn.preprocessing import StandardScaler
    from sksurv.ensemble import GradientBoostingSurvivalAnalysis, RandomSurvivalForest
    from sksurv.linear_model import CoxPHSurvivalAnalysis
    from sksurv.metrics import concordance_index_censored

    X_train, y_train = X[dummies["train"]], y[dummies["train"]]
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    med_time_obs = float(np.median(ds.loc[dummies["train"] & (ds["event_flag"] == 1), "time_to_event"]))
    median_uncensored = float(np.median(ds.loc[dummies["train"], "time_to_event"]))

    models = [
        ("dummy_median_time", None, False),
        ("cox_ph", CoxPHSurvivalAnalysis(alpha=1e-3, tol=1e-6, n_iter=200), False),
        ("random_survival_forest", RandomSurvivalForest(n_estimators=200, min_samples_split=50, max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1), True),
        ("gradient_boosting_survival", GradientBoostingSurvivalAnalysis(loss="coxph", learning_rate=0.05, max_depth=3, n_estimators=200, random_state=RANDOM_STATE), True),
    ]

    rows = []
    summary = [
        "# Proper survival modelling — time_to_next_turning_days (review item 2)",
        "",
        "Previous v1.x 'survival' ran an HGB on the ~9% uncensored rows only (survivorship bias);",
        "this run trains CoxPH / RSF / GBSA on the full train set with per-wheelset observation-end",
        "censoring, and reports a true Harrell C-index over the whole val/test split.",
        "",
        "Right-censoring: `time = last measurement − interval_end` (per-wheelset verified end,",
        "per the phase3 target-evaluation contract), event=0; uncensored rows keep their event time.",
        "",
        f"Train n={int(dummies['train'].sum()):,} (censor {ds.loc[dummies['train'], 'event_flag'].mean():.1%})"
        f" · val n={int(dummies['val'].sum()):,} · test n={int(dummies['test'].sum()):,}.",
        "",
        "| model | split | c_index | n (evaluated) |",
        "| --- | ---: | ---: | ---: |",
    ]

    for name, model, use_raw in models:
        if model is None:
            risk = {"val": np.full(dummies["val"].sum(), -med_time_obs), "test": np.full(dummies["test"].sum(), -med_time_obs)}
        else:
            fit_X = X_train if use_raw else X_train_s
            model.fit(fit_X, y_train)
            risk = {}
            for split_name in ("val", "test"):
                X_e = X[dummies[split_name]] if use_raw else scaler.transform(X[dummies[split_name]])
                risk[split_name] = np.asarray(model.predict(X_e), dtype=float)

        for split_name in ("val", "test"):
            time_eval = ds.loc[dummies[split_name], "time_to_event"].to_numpy()
            event_eval = ds.loc[dummies[split_name], "event_flag"].to_numpy().astype(int)
            c, n_conc, n_disc, n_tied, n_c = concordance_index_censored(event_eval.astype(bool), time_eval, risk[split_name])
            metrics = {"c_index": round(float(c), 4), "n_concordant": int(n_conc), "n_discordant": int(n_disc), "n_tied": int(n_tied), "n": int(n_c)}
            config = {
                "phase": "v1.2_survival",
                "task": "survival",
                "label": SURVIVAL_LABEL,
                "model": name,
                "split_contract": "grouped temporal train/val/test by wheelset median interval-end",
                "censoring": "per-wheelset observation end (last measurement - interval_end); event=1 on turning",
                "note": "trained/scaled on full train; Cox/RFS/GBSA from scikit-survival; true Harrell C-index",
                "random_state": RANDOM_STATE,
            }
            experiment_id, run_dir = create_run(EXPERIMENTS_ROOT, "survival", config)
            write_metrics(run_dir, {split_name: metrics})
            if model is not None:
                write_model(run_dir, model)
            write_predictions(run_dir, pd.DataFrame({
                "operational_exposure_id": ds.loc[dummies[split_name], "operational_exposure_id"],
                "split": split_name,
                "time_to_event": time_eval,
                "event": event_eval,
                "risk_score": risk[split_name],
            }))
            write_manifest(run_dir, {"dataset_version": "v1.2", "feature_store_version": "1.0.0", "feature_spec_version": "1.0.0", "label_spec_version": "1.0.1", "survival_learner": name})
            rows.append({"experiment": f"experiment_{experiment_id:04d}", "task": "survival", "label": SURVIVAL_LABEL, "model": name, "split": split_name, "c_index": metrics["c_index"], "n": metrics["n"]})
            summary.append(f"| {name} | {split_name} | {metrics['c_index']:.4f} | {metrics['n']:,} |")

        # feature importance for tree learners
        if name in ("random_survival_forest",) and model is not None:
            importances = getattr(model, "feature_importances_", None)
            if importances is not None:
                rank = pd.Series(importances, index=features).sort_values(ascending=False)
                write_feature_importance(run_dir, {"kind": "importance", "top_30": rank.head(30).to_dict()})
        if name == "cox_ph" and model is not None:
            coef = np.asarray(getattr(model, "coef_", []))
            if coef.size:
                rank = pd.Series(coef, index=features).sort_values(key=np.abs, ascending=False)
                write_feature_importance(run_dir, {"kind": "coefficients", "top_30": rank.head(30).to_dict()})

    (EXPERIMENTS_ROOT / "comparison.csv").write_text(
        pd.DataFrame(rows).sort_values(["model", "split"]).to_csv(index=False), encoding="utf-8"
    )
    (EXPERIMENTS_ROOT / "comparison_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"wrote -> {EXPERIMENTS_ROOT}")
    print("\n".join(summary))


if __name__ == "__main__":
    main()