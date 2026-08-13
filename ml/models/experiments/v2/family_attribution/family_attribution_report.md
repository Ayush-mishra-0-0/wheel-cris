# WS4 Family Attribution — LightGBM (v2.0, grouped test)

Full-set test RMSE = 14.467. SHAP matrix from WS2 (interpretability/experiment_0001).

## SHAP family attribution

| family | Σ\|mean SHAP\| | share % | per-feature mean | dominant-row % |
| --- | ---: | ---: | ---: | ---: |
| physics | 14.646 | 46.1 | 0.732 | 89.9 |
| geometry | 8.585 | 27.0 | 0.477 | 10.0 |
| exposure_v2 | 2.987 | 9.4 | 0.272 | 0.0 |
| operational | 2.906 | 9.1 | 0.108 | 0.0 |
| maintenance | 1.617 | 5.1 | 0.065 | 0.0 |
| identity_temporal | 0.650 | 2.0 | 0.162 | 0.0 |
| physics_v2 | 0.309 | 1.0 | 0.039 | 0.0 |
| behavior | 0.087 | 0.3 | 0.044 | 0.0 |

## Leave-one-in (single-family test RMSE, fresh LightGBM fits)

| family | RMSE alone |
| --- | ---: |
| geometry | 14.908 |
| physics | 15.400 |
| physics_v2 | 21.556 |
| identity_temporal | 21.898 |
| maintenance | 22.545 |
| behavior | 23.239 |
| exposure_v2 | 23.445 |
| operational | 23.809 |

## Drop-family agreement (full vs LOO predictions)

| removed | Pearson | mean \|Δpred\| | LOO RMSE |
| --- | ---: | ---: | ---: |
| operational | 0.9877 | 1.893 | 14.566 |
| maintenance | 0.9881 | 1.866 | 14.700 |
| exposure_v2 | 0.9910 | 1.622 | 14.512 |
| physics | 0.9927 | 1.410 | 14.439 |
| identity_temporal | 0.9933 | 1.346 | 14.484 |
| geometry | 0.9938 | 1.298 | 14.463 |
| behavior | 0.9945 | 1.228 | 14.439 |
| physics_v2 | 0.9945 | 1.221 | 14.462 |

## Interpretation

- physics dominates SHAP sum but has 20 features; per-feature mean is the
  size-fair comparison (geometry ≈ physics per feature).
- Drop-family displacement measures how much each family moves predictions;
  a family can be low-SHAP yet high-displacement if it acts on few rows.
- exposure_v2 / physics_v2 SHAP is only driven by post-2023 rows (gated);
  see feature_availability_report.md before reading too much into their
  absolute magnitudes.
