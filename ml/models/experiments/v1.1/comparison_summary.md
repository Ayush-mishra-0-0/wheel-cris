# V1.1 comparison — v1.0 vs v1.1 (physics + measured geometry)

## regression

### next_interval_dia_delta_mm · test

| model | feature_set | rmse |
| --- | --- | --- |
| dummy_mean | v1.0 | 24.4432 |
| dummy_mean | v1.1 | 24.4432 |
| elastic_net | v1.0 | 23.6861 |
| elastic_net | v1.1 | 15.9425 |
| hist_gradient_boosting | v1.0 | 23.1034 |
| hist_gradient_boosting | v1.1 | 15.7024 |
| linear | v1.0 | 22.8811 |
| linear | v1.1 | 15.6882 |
| random_forest | v1.0 | 21.7713 |
| random_forest | v1.1 | 15.7229 |

### next_interval_dia_delta_mm · val

| model | feature_set | rmse |
| --- | --- | --- |
| dummy_mean | v1.0 | 28.2245 |
| dummy_mean | v1.1 | 28.2245 |
| elastic_net | v1.0 | 27.5812 |
| elastic_net | v1.1 | 22.1147 |
| hist_gradient_boosting | v1.0 | 26.3115 |
| hist_gradient_boosting | v1.1 | 22.2135 |
| linear | v1.0 | 27.0223 |
| linear | v1.1 | 21.7971 |
| random_forest | v1.0 | 26.1960 |
| random_forest | v1.1 | 21.9899 |

## binary

### next_interval_large_loss_flag · test

| model | feature_set | pr_auc |
| --- | --- | --- |
| dummy_prior | v1.0 | 0.7154 |
| dummy_prior | v1.1 | 0.7154 |
| hist_gradient_boosting | v1.0 | 0.8446 |
| hist_gradient_boosting | v1.1 | 0.9266 |
| logistic | v1.0 | 0.7680 |
| logistic | v1.1 | 0.9022 |
| random_forest | v1.0 | 0.8527 |
| random_forest | v1.1 | 0.9270 |

### next_interval_large_loss_flag · val

| model | feature_set | pr_auc |
| --- | --- | --- |
| dummy_prior | v1.0 | 0.6314 |
| dummy_prior | v1.1 | 0.6314 |
| hist_gradient_boosting | v1.0 | 0.7850 |
| hist_gradient_boosting | v1.1 | 0.8898 |
| logistic | v1.0 | 0.7145 |
| logistic | v1.1 | 0.8710 |
| random_forest | v1.0 | 0.7883 |
| random_forest | v1.1 | 0.8881 |

### next_interval_turning_flag · test

| model | feature_set | pr_auc |
| --- | --- | --- |
| dummy_prior | v1.0 | 0.0111 |
| dummy_prior | v1.1 | 0.0111 |
| hist_gradient_boosting | v1.0 | 0.0127 |
| hist_gradient_boosting | v1.1 | 0.0135 |
| logistic | v1.0 | 0.0117 |
| logistic | v1.1 | 0.0116 |
| random_forest | v1.0 | 0.0153 |
| random_forest | v1.1 | 0.0140 |

### next_interval_turning_flag · val

| model | feature_set | pr_auc |
| --- | --- | --- |
| dummy_prior | v1.0 | 0.0132 |
| dummy_prior | v1.1 | 0.0132 |
| hist_gradient_boosting | v1.0 | 0.0284 |
| hist_gradient_boosting | v1.1 | 0.0241 |
| logistic | v1.0 | 0.0176 |
| logistic | v1.1 | 0.0184 |
| random_forest | v1.0 | 0.0296 |
| random_forest | v1.1 | 0.0278 |

## survival

### time_to_next_turning_days · test

| model | feature_set | c_index |
| --- | --- | --- |
| dummy_median_time | v1.0 | 0.0000 |
| dummy_median_time | v1.1 | 0.0000 |
| hist_gradient_boosting_observed_only | v1.0 | 0.5392 |
| hist_gradient_boosting_observed_only | v1.1 | 0.5434 |
| random_forest_observed_only | v1.0 | 0.5389 |
| random_forest_observed_only | v1.1 | 0.5429 |

### time_to_next_turning_days · val

| model | feature_set | c_index |
| --- | --- | --- |
| dummy_median_time | v1.0 | 0.0000 |
| dummy_median_time | v1.1 | 0.0000 |
| hist_gradient_boosting_observed_only | v1.0 | 0.5563 |
| hist_gradient_boosting_observed_only | v1.1 | 0.5517 |
| random_forest_observed_only | v1.0 | 0.5680 |
| random_forest_observed_only | v1.1 | 0.5648 |
