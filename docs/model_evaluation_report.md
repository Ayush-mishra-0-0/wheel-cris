# Model Evaluation Report — Two Protocols (v1.0)

**Date:** 2026-08-04
**Dataset:** `model_datasets/v1.0/model_dataset_v1.0.parquet` (202,237 supervised Gold-B intervals, WAP7 cohort, 2015-01 → 2026-07)
**Models:** HistGradientBoosting (sklearn stand-in for LightGBM/CatBoost/XGBoost)

This project reports **two** evaluation protocols because they answer two different
questions (see `docs/continuous_evolution_guide.md` and the domain discussion on
generalisation vs production simulation):

| Protocol | Question it answers | Split |
|---|---|---|
| **Grouped-wheelset split** (v1.0 dataset) | "Can the model learn general wheel-wear physics / work on a wheel never seen before?" | No wheelset appears in >1 fold; temporal train/val/test |
| **Rolling temporal (production sim)** | "If deployed today, how accurately does it predict the *next* inspection as each wheel accumulates history?" | Cutoff date T: train on all `next_interval_end <= T`, evaluate on wheels with `interval_end <= T < next_interval_end` |

---

## 1. Protocol A — Grouped-Wheelset Split (unseen wheels)

From `models/experiments/v1.0/comparison.csv`, **test** split, HistGradientBoosting:

| Task | Target | Metric | Dummy baseline | HGB |
|---|---|---|---|---|
| Regression | `next_interval_dia_delta_mm` | RMSE (mm) | 24.44 (mean) | **23.10** |
| Binary | `next_interval_large_loss_flag` | PR-AUC | 0.715 (prevalence) | **0.845** |
| Binary | `next_interval_turning_flag` | PR-AUC | 0.011 (prevalence) | **0.013** |
| Survival | `time_to_next_turning_days` | C-index | 0.000 (constant risk) | **0.539** |

HGB beats the naive baselines on every task, but the turning-flag task is genuinely
hard (1.1% event rate; PR-AUC ~ prevalence → barely above random).

---

## 2. Protocol B — Rolling Temporal (Production Simulation)

Runs in `models/experiments/v1.0/rolling_eval/cutoff_YYYYMMDD/` (8 cutoffs). At each cutoff
the model is retrained on **all** history before that date and scored on wheels whose
next inspection is still pending — exactly the deployed RUL flow.

### Regression — RMSE over deployment date (lower is better)

| Cutoff | n_train | n_eval | RMSE | MAE | Spearman |
|---|---|---|---|---|---|
| 2016-11-27 | 564 | 1,254 | 249.3 | 143.1 | 0.061 |
| 2018-02-14 | 1,449 | 1,879 | 160.4 | 80.5 | 0.086 |
| 2019-05-04 | 3,897 | 1,974 | 103.1 | 50.1 | 0.251 |
| 2020-07-22 | 9,894 | 1,581 | 46.1 | 38.1 | 0.355 |
| 2021-10-09 | 22,528 | 1,793 | 37.3 | 30.7 | 0.291 |
| 2022-12-28 | 32,858 | 4,607 | 33.4 | 25.7 | 0.252 |
| 2024-03-16 | 50,965 | 8,273 | **31.9** | 24.6 | 0.309 |
| 2025-06-04 | 105,581 | 11,047 | 33.1 | 22.7 | 0.299 |

RMSE falls from 249 → ~32 mm as training history accumulates, i.e. the deployed model
gets materially better as CRIS's data lake grows. The plateau at ~32–33 mm is
**higher than the Protocol-A test RMSE (23.1 mm)** — expected and important:

- Protocol A evaluates on the fixed "latest 15%" temporal test bucket and never
  lets the model see a wheel it later scores (optimistic).
- Protocol B evaluates on the open tail of the dataset (through 2026-07) where
  prediction horizons are heterogeneous and longer, so error is naturally larger.

### Binary — PR-AUC over deployment date (higher is better)

| Cutoff | large_loss PR-AUC | turning PR-AUC |
|---|---|---|
| 2016-11-27 | 0.792 | — (no positives in eval set) |
| 2018-02-14 | 0.746 | — |
| 2019-05-04 | 0.827 | — |
| 2020-07-22 | 0.696 | — |
| 2021-10-09 | 0.741 | — |
| 2022-12-28 | 0.700 | 0.010 |
| 2024-03-16 | 0.705 | 0.006 |
| 2025-06-04 | 0.801 | 0.022 |

Large-loss is robustly predictable (PR-AUC 0.70–0.83 vs 0.615 population prevalence)
across deployment dates — no degradation as data grows. The turning-flag PR-AUC stays
at the population prevalence (~1%) → **not predictable from these features** in either
protocol; treat it as a risk-listing feature, not a driver of decisions.

### Survival — C-index over deployment date (higher is better)

| Cutoff | C-index |
|---|---|
| 2016–2021 cutoffs | undefined (no observed turning events in eval window) |
| 2022-12-28 | 0.505 |
| 2024-03-16 | **0.700** |
| 2025-06-04 | 0.527 |

C-index is only defined once the eval window contains enough observed (uncensored)
turning events. Where measurable it beats the 0.5 random baseline (0.70 at the
2024 cutoff) but fluctuates with eval-set composition.

---

## 3. Protocol A vs Protocol B — the honest comparison

| Target | Grouped-split (unseen) | Production-sim (latest cutoff) |
|---|---|---|
| Regression RMSE | 23.1 mm | 33.1 mm |
| Large-loss PR-AUC | 0.845 | 0.801 |
| Turning PR-AUC | 0.013 | 0.022 |
| Survival C-index | 0.539 | 0.527 |

**Interpretation:** Protocol A is the optimistic ceiling (fixed test bucket, unseen
wheels). Protocol B is what production actually delivers — somewhat worse on regression
(longer/harder horizons at the data tail) but comparable on classification and survival.
Both confirm the same ranking: large-loss is solvable, wear-delta is moderately
predictable, turning-flag is not.

---

## 4. Model artifacts — the "bin file" question

Yes — every trained model is now persisted as a **binary joblib file** in its
experiment directory (`model_<task>.joblib`). There was no `.bin`/`.pkl` before
because the harness only wrote metrics/predictions/importance; this was a gap that is
now closed.

Layout:

```
models/experiments/v1.0/<task>/experiment_XXXX/
    config.json, metrics.json, predictions.parquet
    feature_importance.json, manifest.json
    model.joblib          <-- the trained estimator (sklearn/joblib binary)

models/experiments/v1.0/rolling_eval/cutoff_YYYYMMDD/
    model_regression.joblib
    model_next_interval_large_loss_flag.joblib
    model_next_interval_turning_flag.joblib
    model_survival.joblib
    metrics.json / predictions_<task>.parquet / dataset_card.txt / model_info.json
```

The rolling-eval cutoffs each contain all four task models as separate `.joblib`
files (regression, both binary targets, survival), so each deployment date is fully
reproducible. Models are loaded with `joblib.load(...)` for deployment/inference.
```
