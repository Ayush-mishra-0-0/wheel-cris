# WS1 Benchmark — v2.0 (Phase 2)

Dataset: model_dataset_v2.0 (202,172 rows, 115 features, next_interval_dia_delta_mm).
Missingness: native-NaN for trees; family-median impute + per-family indicators for Linear/RF.

## Grouped temporal (test split)

| model | RMSE (mean±sd) | MAE (mean±sd) | R2 (mean±sd) |
| --- | ---: | ---: | ---: |
| catboost | 14.475±0.017 | 11.179±0.011 | 0.536±0.001 |
| dummy_mean | 23.604±0.000 | 18.674±0.000 | -0.234±0.000 |
| hist_gradient_boosting | 14.498±0.023 | 11.227±0.033 | 0.535±0.001 |
| lightgbm | 14.533±0.007 | 11.283±0.009 | 0.532±0.000 |
| linear | 14.968±0.000 | 11.998±0.000 | 0.504±0.000 |
| random_forest | 14.537±0.005 | 11.285±0.007 | 0.532±0.000 |
| xgboost | 14.516±0.007 | 11.222±0.016 | 0.533±0.000 |

## Rolling production-sim (median across cutoffs)

| model | median RMSE | median MAE |
| --- | ---: | ---: |
| catboost | 29.388 | 25.497 |
| dummy_mean | 36.234 | 29.653 |
| hist_gradient_boosting | 29.620 | 25.640 |
| lightgbm | 29.686 | 25.371 |
| linear | 29.121 | 26.099 |
| random_forest | 28.932 | 24.864 |
| xgboost | 29.620 | 25.357 |

## Caveats

- Exposure-v2 / physics-v2 families are 0% present before 2023 (see feature_availability_report.md);
  in the grouped split their signal is only exploitable on recent rows.
- Rolling is the deployed-predictions simulation; v1.2 HGB was 14.57 grouped vs 29.66 rolling.
