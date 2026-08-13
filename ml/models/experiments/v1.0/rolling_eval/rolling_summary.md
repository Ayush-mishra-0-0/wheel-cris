# Rolling Temporal (Production Simulation) Evaluation — v1.0

Protocol: at each cutoff date T, train on all intervals whose next inspection already occurred (next_interval_end <= T) and evaluate on wheels whose next inspection is still pending (interval_end <= T < next_interval_end). This measures how the deployed system would actually perform, where each wheel accumulates more history over time.

## regression

| cutoff | n_train | n_eval | model | primary |
| --- | --- | --- | --- | --- |
| 2016-11-27 | 564 | 1254 | hgb | 249.3426 |
| 2018-02-14 | 1449 | 1879 | hgb | 160.4223 |
| 2019-05-04 | 3897 | 1974 | hgb | 103.1337 |
| 2020-07-22 | 9894 | 1581 | hgb | 46.1026 |
| 2021-10-09 | 22528 | 1793 | hgb | 37.2712 |
| 2022-12-28 | 32858 | 4607 | hgb | 33.3661 |
| 2024-03-16 | 50965 | 8273 | hgb | 31.9014 |
| 2025-06-04 | 105581 | 11047 | hgb | 33.0819 |

## binary

| cutoff | n_train | n_eval | model | primary |
| --- | --- | --- | --- | --- |
| 2016-11-27 | 564 | 1254 | hgb | nan |
| 2016-11-27 | 564 | 1254 | hgb | 0.7923 |
| 2018-02-14 | 1449 | 1879 | hgb | nan |
| 2018-02-14 | 1449 | 1879 | hgb | 0.7461 |
| 2019-05-04 | 3897 | 1974 | hgb | nan |
| 2019-05-04 | 3897 | 1974 | hgb | 0.8268 |
| 2020-07-22 | 9894 | 1581 | hgb | nan |
| 2020-07-22 | 9894 | 1581 | hgb | 0.6962 |
| 2021-10-09 | 22528 | 1793 | hgb | nan |
| 2021-10-09 | 22528 | 1793 | hgb | 0.7412 |
| 2022-12-28 | 32858 | 4607 | hgb | 0.01 |
| 2022-12-28 | 32858 | 4607 | hgb | 0.6997 |
| 2024-03-16 | 50965 | 8273 | hgb | 0.0058 |
| 2024-03-16 | 50965 | 8273 | hgb | 0.7053 |
| 2025-06-04 | 105581 | 11047 | hgb | 0.0224 |
| 2025-06-04 | 105581 | 11047 | hgb | 0.8009 |

## survival

| cutoff | n_train | n_eval | model | primary |
| --- | --- | --- | --- | --- |
| 2016-11-27 | 564 | 1254 | hgb | 0.0 |
| 2018-02-14 | 1449 | 1879 | hgb | nan |
| 2019-05-04 | 3897 | 1974 | hgb | nan |
| 2020-07-22 | 9894 | 1581 | hgb | nan |
| 2021-10-09 | 22528 | 1793 | hgb | nan |
| 2022-12-28 | 32858 | 4607 | hgb | 0.5054 |
| 2024-03-16 | 50965 | 8273 | hgb | 0.6999 |
| 2025-06-04 | 105581 | 11047 | hgb | 0.5265 |
