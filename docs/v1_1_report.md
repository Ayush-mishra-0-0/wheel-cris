# V1.1 — Model Understanding & Physics-Informed Enhancement

**Status:** complete · **Split contract:** grouped temporal (wheelset median interval-end) · **Label spec:** 1.0.0

## 1. Motivation

v1.0 exposed only *interval deltas* (e.g. `diameter_delta_raw_mm_side_1`) plus
context. The absolute measured wheel geometry at the prediction timestamp
(`interval_end`) — the current diameter, root, flange, tread and tire thickness —
was present in the raw measurements but **excluded from the model dataset**.

This mattered because that absolute state is exactly what a maintenance engineer
knows when deciding on the next interval. A wheel's current diameter is the
physical anchor for how much material remains and therefore how it will wear.

## 2. What was added (point-in-time safe, existing data only)

A per-measurement augmentation table (`model_datasets/physics_features.py`) joined
on `interval_end_measurement_id` (99.5% match, rest median-imputed on train):

| Group | Prefix | Examples | # |
| --- | --- | --- | --- |
| Raw measured geometry at interval end | `geom_` | `geom_wsmDia1/2`, `geom_wsmRoot1/2`, `geom_wsmFlange1/2`, `geom_wsmWear`, `geom_wsmTireThikness1/2`, `geom_wsmWearRate`, `geom_wsmFlangeThickness1/2` | 18 |
| Level 1 material state | `phys_` | `phys_remaining_material_mm_s1/s2` = current dia − 1016, `phys_wear_fraction_s1/s2` = (current−1016)/(initial−1016), `phys_material_consumed_pct`, `phys_initial_dia_mm` | 10 |
| Level 2 wear trends | `phys_` | `phys_cumulative_wear_mm`, `phys_interval_wear_rate`, `phys_wear_acceleration`, `phys_ema_wear_rate` (halflife 3), `phys_remaining_budget_days` | 10 |
| Life-cycle state | `phys_` | `phys_turning_events_cumulative`, `phys_wheelset_age_days` | 2 |

Domain constants (from owner): **new diameter 1096 mm, condemning 1016 mm.**
All features are computed as-of each measurement timestamp — no future leakage.
Dataset: `model_datasets/v1.1/` (98 X features), validation **PASS**.

## 3. Results (TEST split, identical split/labels as v1.0)

### Regression — `next_interval_dia_delta_mm`

| model | RMSE v1.0 | RMSE v1.1 | Δ |
| --- | ---: | ---: | ---: |
| linear | 22.88 | **15.69** | −31% |
| elastic_net | 23.69 | 15.94 | −33% |
| hist_gradient_boosting | 23.10 | **15.70** | −32% |
| random_forest | 21.77 | **15.72** | −28% |

MAE 16.54 → 11.68 (−29%) · p95 error 45.1 → 30.4 · Spearman 0.353 → 0.636

### Binary — `next_interval_large_loss_flag`

| model | PR-AUC v1.0 | PR-AUC v1.1 | Δ |
| --- | ---: | ---: | ---: |
| logistic | 0.768 | **0.902** | +0.134 |
| hist_gradient_boosting | 0.845 | **0.927** | +0.082 |
| random_forest | 0.853 | **0.927** | +0.074 |

### Binary — `next_interval_turning_flag` (unchanged)
Turning remains ~1.1% positive with PR-AUC ≈ prevalence (0.013–0.016) in both
versions — the physics features do not create signal where none exists.

### Survival — `time_to_next_turning_days` (flat)
C-index 0.539 → 0.543. Survival is dominated by censoring (91%); proper survival
models are still future work.

## 4. Ablation — which feature group drives the gain?

HGB test metrics, four variants of the SAME v1.0 rows:

| task | v1.0 | +geom | +phys | +all |
| --- | ---: | ---: | ---: | ---: |
| regression RMSE | 23.10 | **15.65** | 16.50 | 15.70 |
| large-loss PR-AUC | 0.845 | **0.928** | 0.922 | 0.927 |

**Finding:** exposing the raw measured geometry (`geom_*`) is the single largest
contribution (RMSE 23.10 → 15.65). The engineered physics features (`phys_*`)
deliver most of their value *because* they encode the same absolute diameter into
material-remaining terms; the two largely overlap (corr ~1.0), so combining them
adds little beyond geometry alone. This confirms the user's hypothesis: the
absolute current geometry was the missing high-value signal, not new data.

## 5. Permutation importance (HGB regression, v1.1)

1. `phys_remaining_material_mm_s2` (2.5× the next feature)
2. `phys_remaining_material_mm_s1`
3. `diameter_delta_raw_mm_side_1`
4. `geom_wsmTireThikness1/2`
5. `phys_remaining_budget_days_*`, `phys_ema_wear_rate_*`

## 6. Residual / error analysis

`models/experiments/v1.1/error_analysis/` — worst-100 + per-strata MAE change:

- MAE improved **30–55% in every shed stratum** (PADX −55%, ETE −48%, GMOE −47%).
- The worst shed in v1.0 (PADX, 11× enrichment) **left the worst-100 entirely**.
- Remaining worst-100 errors are dominated by label sentinels (e.g. y_true
  ≈ +1050 mm) and genuinely surprising intervals — not shed/geometry patterns.
- Turning/RTIS-coverage strata no longer concentrate errors.

## 7. Deployment implication (Protocol B preview)

The gains hold under the grouped-split protocol used here. Because the added
features are all *current-state at prediction time*, they are available in the
rolling/production protocol with the same point-in-time semantics — a natural next
validation step before promoting v1.1 to champion.

## 8. Caveats / next steps

1. `shap` is not installed; attribution used permutation importance. Installing
   `shap` would add per-row explanations for the physics features.
2. The v1.1 regression label still contains sentinel outliers (min/max ±1090 mm)
   inflating RMSE; a quarantined label version (label_spec ≥ 1.1) should follow.
3. Side-2 physics features correlate ~1.0 with side-1 (diameter 1/2 corr 0.998);
   consider dropping one side for the linear/ElasticNet models.
4. Survival task needs a proper survival learner (Cox / RandomSurvivalForest)
   before V1.1 can claim improvement there.
5. Recommend a rolling-temporal evaluation (Protocol B) on v1.1 to confirm the
   grouped-split gain transfers to the production simulation before V2.0.

## Artifacts

- `model_datasets/physics/physics_features_v1.1.parquet` + manifest
- `model_datasets/v1.1/model_dataset_v1.1.parquet` + manifest + card + validation_report (PASS)
- `models/experiments/v1.1/` — 64 runs (comparison.csv, comparison_summary.md)
- `models/experiments/v1.1/ablation/ablation.csv`
- `models/experiments/v1.1/error_analysis/` (regression_strata_improvement.csv, worst_100_v1_1_regression.csv, residual_summary.md)
