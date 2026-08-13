# WS5 Ablation — family-level (v2.0, grouped test)

## Leave-one-out (RMSE delta vs full set)

| model | removed family | full RMSE | LOO RMSE | ΔRMSE |
| --- | --- | ---: | ---: | ---: |
| linear | maintenance | 14.968 | 15.234 | +0.266 |
| lightgbm | maintenance | 14.467 | 14.700 | +0.233 |
| linear | operational | 14.968 | 15.136 | +0.168 |
| lightgbm | operational | 14.467 | 14.566 | +0.099 |
| lightgbm | exposure_v2 | 14.467 | 14.512 | +0.045 |
| linear | physics | 14.968 | 14.996 | +0.028 |
| linear | geometry | 14.968 | 14.989 | +0.021 |
| lightgbm | identity_temporal | 14.467 | 14.484 | +0.018 |
| linear | behavior | 14.968 | 14.966 | -0.002 |
| lightgbm | geometry | 14.467 | 14.463 | -0.003 |
| linear | identity_temporal | 14.968 | 14.964 | -0.004 |
| lightgbm | physics_v2 | 14.467 | 14.462 | -0.005 |
| linear | physics_v2 | 14.968 | 14.956 | -0.012 |
| lightgbm | physics | 14.467 | 14.439 | -0.027 |
| lightgbm | behavior | 14.467 | 14.439 | -0.028 |
| linear | exposure_v2 | 14.968 | 14.930 | -0.038 |

## Forward selection (lightgbm)

| step | added family | RMSE | Δ step | vs full-set |
| --- | --- | ---: | ---: | ---: |
| 1 | geometry | 14.908 | +8.696 | -0.442 |
| 2 | exposure_v2 | 14.595 | +0.313 | -0.129 |
| 3 | maintenance | 14.516 | +0.080 | -0.049 |
| 4 | operational | 14.425 | +0.090 | +0.041 |
| 5 | behavior | 14.417 | +0.008 | +0.049 |
| 6 | identity_temporal | 14.415 | +0.003 | +0.052 |
| 7 | physics_v2 | 14.450 | -0.036 | +0.016 |
| 8 | physics | 14.475 | -0.025 | -0.009 |

## Forward selection (linear)

| step | added family | RMSE | Δ step | vs full-set |
| --- | --- | ---: | ---: | ---: |
| 1 | geometry | 15.023 | +8.581 | -0.056 |
| 2 | maintenance | 14.882 | +0.141 | +0.086 |
| 3 | identity_temporal | 14.880 | +0.002 | +0.088 |
| 4 | behavior | 14.880 | -0.001 | +0.088 |
| 5 | physics | 14.888 | -0.008 | +0.080 |
| 6 | physics_v2 | 14.900 | -0.012 | +0.067 |
| 7 | operational | 14.930 | -0.029 | +0.038 |
| 8 | exposure_v2 | 14.968 | -0.038 | +0.000 |

## Test availability (rows with the family present)

| family | availability |
| --- | ---: |
| behavior | 1.000 |
| geometry | 1.000 |
| physics | 1.000 |
| maintenance | 1.000 |
| operational | 1.000 |
| identity_temporal | 1.000 |
| exposure_v2 | 0.533 |
| physics_v2 | 0.479 |

## Caveats

- LOO deltas are averaged over all test rows; families present only post-2023
  (exposure_v2, physics_v2) show diluted deltas. See availability_normalized.csv
  for the same deltas restricted to rows where the family is present.
- For trees, a dropped family becomes all-NaN columns; for linear, its columns
  and its missingness indicator are both removed.
