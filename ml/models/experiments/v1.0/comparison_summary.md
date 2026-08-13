# Baseline comparison (v1.0)

## regression

| model | label | split | metric | value |
| --- | --- | --- | --- | --- |
| dummy_mean | next_interval_dia_delta_mm | test | rmse | 24.4432 |
| dummy_mean | next_interval_dia_delta_mm | val | rmse | 28.2245 |
| dummy_median | next_interval_dia_delta_mm | test | rmse | 24.3961 |
| dummy_median | next_interval_dia_delta_mm | val | rmse | 28.2004 |
| elastic_net | next_interval_dia_delta_mm | test | rmse | 23.6861 |
| elastic_net | next_interval_dia_delta_mm | val | rmse | 27.5812 |
| hist_gradient_boosting | next_interval_dia_delta_mm | test | rmse | 23.1034 |
| hist_gradient_boosting | next_interval_dia_delta_mm | val | rmse | 26.3115 |
| linear | next_interval_dia_delta_mm | test | rmse | 22.8811 |
| linear | next_interval_dia_delta_mm | val | rmse | 27.0223 |

## binary

| model | label | split | metric | value |
| --- | --- | --- | --- | --- |
| dummy_majority | next_interval_large_loss_flag | test | pr_auc | 0.7154 |
| dummy_majority | next_interval_large_loss_flag | val | pr_auc | 0.6314 |
| dummy_majority | next_interval_turning_flag | test | pr_auc | 0.0111 |
| dummy_majority | next_interval_turning_flag | val | pr_auc | 0.0132 |
| dummy_prior | next_interval_large_loss_flag | test | pr_auc | 0.7154 |
| dummy_prior | next_interval_large_loss_flag | val | pr_auc | 0.6314 |
| dummy_prior | next_interval_turning_flag | test | pr_auc | 0.0111 |
| dummy_prior | next_interval_turning_flag | val | pr_auc | 0.0132 |
| hist_gradient_boosting | next_interval_large_loss_flag | test | pr_auc | 0.8446 |
| hist_gradient_boosting | next_interval_large_loss_flag | val | pr_auc | 0.785 |
| hist_gradient_boosting | next_interval_turning_flag | test | pr_auc | 0.0127 |
| hist_gradient_boosting | next_interval_turning_flag | val | pr_auc | 0.0284 |
| logistic | next_interval_large_loss_flag | test | pr_auc | 0.768 |
| logistic | next_interval_large_loss_flag | val | pr_auc | 0.7145 |
| logistic | next_interval_turning_flag | test | pr_auc | 0.0117 |
| logistic | next_interval_turning_flag | val | pr_auc | 0.0176 |

## survival

| model | label | split | metric | value |
| --- | --- | --- | --- | --- |
| dummy_median_time | time_to_next_turning_days | test | c_index | 0.0 |
| dummy_median_time | time_to_next_turning_days | val | c_index | 0.0 |
| hist_gradient_boosting_observed_only | time_to_next_turning_days | test | c_index | 0.5392 |
| hist_gradient_boosting_observed_only | time_to_next_turning_days | val | c_index | 0.5563 |
