# Phase 3B - Prediction intervals on next-state degradation

80% prediction intervals (10th/90th quantile XGBoost) on the next measured
state per dimension, measured on held-out chronological data.

| Dimension | n | Empirical coverage | Target | Gap (pts) | Mean width (mm) | p90 width (mm) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wsmDia | 48,674 | 85.7% | 80% | +0.057 | 11.041 | 18.422 |
| wsmFlangeThickness | 48,674 | 79.2% | 80% | -0.008 | 2.570 | 6.478 |
| wsmRoot | 48,656 | 86.4% | 80% | +0.064 | 2.473 | 3.148 |

## Interpretation

- Coverage near 80% = the uncertainty band is honest (well calibrated).
- Coverage well below 80% = intervals too narrow (overconfident).
- Width in mm is the practical uncertainty: e.g. diameter interval +/- X mm.
- Same chronological split and reset exclusion as the degradation model.
