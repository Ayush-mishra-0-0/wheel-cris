"""WS1 — Benchmark suite (Phase 2): 6 models x grouped + rolling protocols x seeds.

Models: linear, random_forest, hist_gradient_boosting, lightgbm, catboost, xgboost.
Task: regression `next_interval_dia_delta_mm` on the v2.0 dataset (115 features).

Protocols (both reported — see feature_availability_report.md for why):
  - grouped temporal: fit on split=='train', evaluate on val/test (grouped by
    wheelset, 70/15/15 by interval_end_timestamp). Fast; the in-distribution number.
  - rolling production-sim: at each cutoff T, train on next_interval_end <= T and
    evaluate on interval_end <= T < next_interval_end (the deployed predictions).
    The honest number (v1.2 showed grouped 14.57 vs rolling 29.66).

Missingness policy (locked by owner):
  - trees (HGB/LGBM/CatBoost/XGB): native NaN handling, raw X.
  - linear/random_forest: family-consistent median imputation + ONE missingness
    indicator per family (8), fit on the train fold only.

Hyperparameters are fixed/documented (baseline phase, no search). Every fit is
persisted through the experiment registry (never overwrites).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.experiment_registry import (create_run, write_feature_importance,  # noqa: E402
                                        write_manifest, write_metrics, write_model,
                                        write_predictions)
from models.phase2.families import FAMILY_ORDER, feature_families  # noqa: E402

DATASET = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
MANIFEST = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_manifest_v2.0.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"

REGRESSION_LABEL = "next_interval_dia_delta_mm"
GROUPED_SEEDS = [7, 42, 1337]
ROLLING_SEEDS = [42]
N_CUTOFFS = 8


def _estimator(model_name: str, seed: int):
    if model_name == "dummy_mean":
        return DummyRegressor(strategy="mean")
    if model_name == "linear":
        return Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                         ("scale", StandardScaler()), ("reg", LinearRegression())])
    if model_name == "random_forest":
        return Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                         ("reg", RandomForestRegressor(n_estimators=150, max_depth=18,
                                                       min_samples_leaf=25, n_jobs=-1,
                                                       random_state=seed))])
    if model_name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(max_iter=200, learning_rate=0.1,
                                             early_stopping=True, validation_fraction=0.15,
                                             n_iter_no_change=20, random_state=seed)
    if model_name == "lightgbm":
        import lightgbm as lgb
        return lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=63,
                                 subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                                 random_state=seed, verbosity=-1)
    if model_name == "catboost":
        import catboost as cb
        return cb.CatBoostRegressor(iterations=500, learning_rate=0.05, depth=6,
                                    verbose=0, random_seed=seed)
    if model_name == "xgboost":
        import xgboost as xgb
        return xgb.XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=6,
                                subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                                random_state=seed)
    raise ValueError(model_name)


def _load():
    dataset = pd.read_parquet(DATASET)
    fams = feature_families(MANIFEST)
    x_cols = [c for cols in fams.values() for c in cols]
    return dataset, fams, x_cols


def _augmented_x(df: pd.DataFrame, fams: dict[str, list[str]], x_cols: list[str]):
    """Family-consistent imputation + per-family missing indicators (Linear/RF)."""
    X = df[x_cols].copy()
    indicators = []
    for fam in FAMILY_ORDER:
        cols = [c for c in fams[fam]]
        indicators.append((X[cols].isna().any(axis=1).astype(int)).rename(f"miss_{fam}"))
    return X, pd.concat(indicators, axis=1)


def _importance(model, X, y, x_cols, x_aug_cols, native: bool, seed: int) -> dict:
    if native:
        try:
            import lightgbm, catboost, xgboost
            imp = getattr(model, "feature_importances_", None)
            if imp is not None and len(imp) == len(x_aug_cols):
                return {"kind": "native", "top_30": dict(
                    pd.Series(imp, index=x_aug_cols).sort_values(ascending=False).head(30))}
        except Exception:
            pass
    try:
        from sklearn.inspection import permutation_importance
        perm = permutation_importance(model, X, y, n_repeats=3, random_state=seed,
                                      scoring="neg_mean_squared_error", n_jobs=-1)
        rank = pd.Series(perm.importances_mean, index=x_aug_cols).sort_values(ascending=False)
        return {"kind": "permutation", "scorer": "neg_mean_squared_error", "top_30": rank.head(30).to_dict()}
    except Exception:
        return {"kind": "unavailable"}


def run_grouped(models, seeds, skip_existing=True) -> list[dict]:
    dataset, fams, x_cols = _load()
    X_full, X_miss = _augmented_x(dataset, fams, x_cols)
    x_use = x_cols + list(X_miss.columns)
    rows = []

    for model_name in models:
        for seed in seeds:
            train_mask = dataset["split"] == "train"
            Xtr, Xva, Xte = X_full[train_mask], X_full[dataset["split"] == "val"], X_full[dataset["split"] == "test"]
            ytr = dataset.loc[train_mask, REGRESSION_LABEL]
            if model_name in ("linear", "random_forest"):
                Xtr = pd.concat([Xtr, X_miss[train_mask]], axis=1)
                Xva = pd.concat([Xva, X_miss[dataset["split"] == "val"]], axis=1)
                Xte = pd.concat([Xte, X_miss[dataset["split"] == "test"]], axis=1)
            else:
                Xtr, Xva, Xte = Xtr[x_cols], Xva[x_cols], Xte[x_cols]
                x_use = x_cols

            est = _estimator(model_name, seed)
            est.fit(Xtr, ytr)
            for split_name, Xev, ye in (("val", Xva, dataset.loc[dataset["split"] == "val", REGRESSION_LABEL]),
                                        ("test", Xte, dataset.loc[dataset["split"] == "test", REGRESSION_LABEL])):
                y_pred = est.predict(Xev)
                metrics = evaluate.regression_metrics(ye, y_pred)
                config = {"phase": "phase2", "workstream": "WS1_benchmark", "protocol": "grouped",
                          "model": model_name, "label": REGRESSION_LABEL, "split": split_name,
                          "random_state": seed, "missingness": "native_nan" if model_name not in
                          ("linear", "random_forest") else "family_median+indicators"}
                exp_id, run_dir = create_run(EXPERIMENTS_ROOT, "benchmark_grouped", config)
                write_metrics(run_dir, metrics)
                write_feature_importance(run_dir, _importance(est, Xev, ye, x_cols, x_use, False, seed))
                write_model(run_dir, est)
                write_predictions(run_dir, pd.DataFrame({
                    "operational_exposure_id": dataset.loc[dataset["split"] == split_name, "operational_exposure_id"].values,
                    "split": split_name, "y_true": ye.values, "y_pred": y_pred}))
                write_manifest(run_dir, {"dataset_version": "v2.0", "feature_spec_version": "1.0.0",
                                         "label_spec_version": "1.0.1"})
                rows.append({"experiment": f"experiment_{exp_id:04d}", "model": model_name,
                             "protocol": "grouped", "split": split_name, "seed": seed, **metrics})
                print(f"  grouped {model_name:24s} seed={seed} {split_name}: RMSE={metrics['rmse']:.3f}")
    return rows


def _cutoffs(dataset: pd.DataFrame, n: int) -> list[pd.Timestamp]:
    lo, hi = dataset["next_interval_end_timestamp"].min(), dataset["next_interval_end_timestamp"].max()
    span = (hi - lo).days
    start, end = lo + pd.Timedelta(days=int(span * 0.15)), hi - pd.Timedelta(days=int(span * 0.10))
    return [start + pd.Timedelta(days=(end - start).days * i / (n - 1)) for i in range(n)]


def run_rolling(models, seeds, n_cutoffs=N_CUTOFFS) -> list[dict]:
    dataset, fams, x_cols = _load()
    cutoffs = _cutoffs(dataset, n_cutoffs)
    rows = []

    for model_name in models:
        for seed in seeds:
            est_template = _estimator(model_name, seed)
            for cutoff in cutoffs:
                next_end = dataset["next_interval_end_timestamp"]
                end = dataset["interval_end_timestamp"]
                train_df = dataset[next_end <= cutoff]
                eval_df = dataset[(end <= cutoff) & (cutoff < next_end)]
                if len(train_df) < 500 or len(eval_df) < 100:
                    continue
                train_df = train_df.reset_index(drop=True)
                eval_df = eval_df.reset_index(drop=True)
                Xtr = train_df[x_cols].copy()
                Xev = eval_df[x_cols].copy()
                if model_name == "hist_gradient_boosting":
                    keep = [c for c in x_cols if train_df[c].nunique(dropna=True) > 1]
                    Xtr = Xtr[keep]
                    Xev = Xev[keep]
                if model_name in ("linear", "random_forest"):
                    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
                    Xtr = imputer.fit_transform(Xtr)
                    Xev = imputer.transform(Xev)
                    Xtr = pd.DataFrame(Xtr, columns=x_cols)
                    Xev = pd.DataFrame(Xev, columns=x_cols)
                    ind_tr = pd.DataFrame({f"miss_{f}": (train_df[[c for c in fams[f]]].isna().any(axis=1).astype(int)) for f in FAMILY_ORDER})
                    ind_ev = pd.DataFrame({f"miss_{f}": (eval_df[[c for c in fams[f]]].isna().any(axis=1).astype(int)) for f in FAMILY_ORDER})
                    Xtr = pd.concat([Xtr, ind_tr], axis=1)
                    Xev = pd.concat([Xev, ind_ev], axis=1)
                est = est_template
                if model_name == "hist_gradient_boosting":
                    est = _estimator(model_name, seed)
                est.fit(Xtr, train_df[REGRESSION_LABEL])
                y_pred = est.predict(Xev)
                metrics = evaluate.regression_metrics(eval_df[REGRESSION_LABEL], y_pred)
                rows.append({"model": model_name, "protocol": "rolling", "cutoff": cutoff.date().isoformat(),
                             "n_train": len(train_df), "n_eval": len(eval_df), "seed": seed, **metrics})
                print(f"  rolling {model_name:24s} seed={seed} cutoff={cutoff.date()}: RMSE={metrics['rmse']:.3f}")
    return rows


def _grouped_from_disk() -> list[dict]:
    """Reconstruct grouped rows from the persisted experiment registry."""
    base = EXPERIMENTS_ROOT / "benchmark_grouped"
    if not base.exists():
        return []
    rows = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        cfg = json.loads((d / "config.json").read_text())
        met = json.loads((d / "metrics.json").read_text())
        rows.append({"experiment": d.name, "model": cfg["model"], "protocol": "grouped",
                     "split": cfg["split"], "seed": cfg["random_state"], **met})
    return rows


def _rolling_from_disk() -> list[dict]:
    out = EXPERIMENTS_ROOT / "benchmark_rolling_rows.parquet"
    if not out.exists():
        return []
    df = pd.read_parquet(out)
    return df.to_dict("records")


def _save_rolling(rows: list[dict]) -> None:
    if not rows:
        return
    pd.DataFrame(rows).to_parquet(EXPERIMENTS_ROOT / "benchmark_rolling_rows.parquet", index=False)


def _summary(grouped_rows, rolling_rows) -> Path:
    if not grouped_rows:
        grouped_rows = _grouped_from_disk()
    if not rolling_rows:
        rolling_rows = _rolling_from_disk()
    g = pd.DataFrame(grouped_rows)
    r = pd.DataFrame(rolling_rows)
    g_test = g[g["split"] == "test"] if len(g) else g
    g_val = g[g["split"] == "val"] if len(g) else g
    lines = [
        "# WS1 Benchmark — v2.0 (Phase 2)",
        "",
        f"Dataset: model_dataset_v2.0 (202,172 rows, 115 features, {REGRESSION_LABEL}).",
        "Missingness: native-NaN for trees; family-median impute + per-family indicators for Linear/RF.",
        "",
        "## Grouped temporal (test split)",
        "",
        "| model | RMSE (mean±sd) | MAE (mean±sd) | R2 (mean±sd) |",
        "| --- | ---: | ---: | ---: |",
    ]
    if len(g_test):
        for m, grp in g_test.groupby("model"):
            if grp["rmse"].notna().sum() == 0:
                continue
            rm = grp["rmse"].mean(); rss = grp["rmse"].std()
            ma = grp["mae"].mean(); mas = grp["mae"].std()
            r2 = grp["r2"].mean(); r2s = grp["r2"].std()
            lines.append(f"| {m} | {rm:.3f}±{rss:.3f} | {ma:.3f}±{mas:.3f} | {r2:.3f}±{r2s:.3f} |")
    else:
        lines.append("| (grouped not run) | — | — | — |")
    lines += ["", "## Rolling production-sim (median across cutoffs)", "",
              "| model | median RMSE | median MAE |", "| --- | ---: | ---: |"]
    if len(r):
        for m, grp in r.groupby("model"):
            lines.append(f"| {m} | {grp['rmse'].median():.3f} | {grp['mae'].median():.3f} |")
    else:
        lines.append("| (rolling not run) | — | — |")
    lines += ["", "## Caveats",
              "",
              "- Exposure-v2 / physics-v2 families are 0% present before 2023 (see feature_availability_report.md);",
              "  in the grouped split their signal is only exploitable on recent rows.",
              "- Rolling is the deployed-predictions simulation; v1.2 HGB was 14.57 grouped vs 29.66 rolling."]
    out = EXPERIMENTS_ROOT / "benchmark_summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--protocols", nargs="+", default=["grouped", "rolling"])
    parser.add_argument("--grouped-seeds", type=int, default=GROUPED_SEEDS, nargs="*")
    args = parser.parse_args()

    models = args.models or ["dummy_mean", "linear", "random_forest", "hist_gradient_boosting",
                             "lightgbm", "catboost", "xgboost"]
    grouped_rows = run_grouped(models, args.grouped_seeds) if "grouped" in args.protocols else []
    rolling_rows = run_rolling(models, ROLLING_SEEDS) if "rolling" in args.protocols else []
    _save_rolling(rolling_rows)
    summary = _summary(grouped_rows, rolling_rows)
    print(f"\n-> {summary.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
