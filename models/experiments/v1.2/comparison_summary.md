# V1.2 comparison — label cleanup effect (v1.1-train vs v1.2-train, same v1.2 test)

Eval rows: v1.2 val=29,734 · v1.2 test=28,065 (v1.1 test was 28,066; the 1 sentinel test row is quarantined in v1.2).

| train_condition | train rows |
| --- | ---: |
| v1_1_train | 144,428 (55 sentinel train labels included) |
| v1_2_train | 144,373 (sentinels quarantined) |

## val

| model | RMSE v1_1_train | RMSE v1_2_train | MAE v1_1_train | MAE v1_2_train | ΔRMSE | ΔMAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dummy_mean | 23.980 | 23.965 | 18.456 | 18.442 | -0.1% | -0.1% |
| elastic_net | 16.618 | 16.585 | 13.358 | 13.369 | -0.2% | +0.1% |
| hist_gradient_boosting | 17.755 | 16.227 | 13.136 | 12.803 | -8.6% | -2.5% |
| linear | 16.793 | 16.573 | 13.339 | 13.317 | -1.3% | -0.2% |
| random_forest | 17.237 | 16.275 | 12.956 | 12.828 | -5.6% | -1.0% |

## test

| model | RMSE v1_1_train | RMSE v1_2_train | MAE v1_1_train | MAE v1_2_train | ΔRMSE | ΔMAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dummy_mean | 23.630 | 23.604 | 18.702 | 18.674 | -0.1% | -0.2% |
| elastic_net | 14.960 | 14.952 | 11.976 | 12.016 | -0.0% | +0.3% |
| hist_gradient_boosting | 15.200 | 14.566 | 11.658 | 11.397 | -4.2% | -2.2% |
| linear | 15.094 | 14.927 | 11.968 | 11.959 | -1.1% | -0.1% |
| random_forest | 14.704 | 14.569 | 11.379 | 11.317 | -0.9% | -0.5% |
