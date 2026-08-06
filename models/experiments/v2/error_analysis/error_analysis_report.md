# WS3 Error Analysis — LightGBM test split (v2.0)

Source: benchmark_grouped/experiment_0006 (lightgbm, seed 42). Overall RMSE=14.535, MAE=11.285, over-predict rate=0.585.

## Sign-stratified error

| sign | n | RMSE | mean residual | exposure present % |
| --- | ---: | ---: | ---: | ---: |
| positive (over-predict wear) | 16430 | 11.792 | 9.893 | 0.483 |
| negative (under-predict wear) | 11635 | 17.699 | -13.251 | 0.604 |

## Worst strata (by RMSE)

| stratum | level | n | RMSE | over-predict % |
| --- | --- | ---: | ---: | ---: |
| interval end year | 2024 | 622 | 18.559 | 0.640 |
| wheel profile | -1.0 | 187 | 18.474 | 0.567 |
| interval end year | 2023 | 62 | 17.538 | 0.677 |
| home shed | ETE | 263 | 17.300 | 0.620 |
| interval end year | 2025 | 11171 | 16.790 | 0.488 |
| turning this interval | 1 | 307 | 16.067 | 0.573 |
| home shed | NGCD | 71 | 16.037 | 0.746 |
| RTIS coverage % | coverage Q4 | 5613 | 15.865 | 0.522 |
| RTIS coverage % | coverage Q5 | 5613 | 15.688 | 0.510 |
| exposure_v2 available | exposure_v2 present | 14968 | 15.498 | 0.531 |
| home shed | SDAD  | 316 | 15.430 | 0.633 |
| home shed | SGUD | 426 | 15.384 | 0.631 |
| home shed | RPME | 333 | 15.294 | 0.607 |
| home shed | <NA> | 7687 | 15.269 | 0.618 |
| home shed | KYNE  | 835 | 15.166 | 0.475 |

## Turning/artifact hypothesis

- Turning intervals: n=307, RMSE=16.067
- Non-turning: n=27758, RMSE=14.517

## Yearly RMSE (exposure-window confound)

| year | n | RMSE |
| --- | ---: | ---: |
| 2019.0 | 3.0 | 19.912 |
| 2020.0 | 2.0 | 23.157 |
| 2021.0 | 5.0 | 29.354 |
| 2022.0 | 9.0 | 13.663 |
| 2023.0 | 62.0 | 17.538 |
| 2024.0 | 622.0 | 18.559 |
| 2025.0 | 11171.0 | 16.790 |
| 2026.0 | 16191.0 | 12.522 |

## Caveats

- Pre-2023 rows have no exposure_v2/physics_v2 signal; their error is driven by
  geometry/physics legacy features only (see feature_availability_report.md).
- Worst-100 rows are enumerated in worst_100.csv for manual inspection.
