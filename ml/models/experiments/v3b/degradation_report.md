# Phase 3B - Engineering State Evolution (next-state model)

Predicts the NEXT measured engineering state (absolute mm) from current
state + exposure. Chronological 80/20 (forward-looking). The **persistence**
baseline (predict current state unchanged) shows the value-add of exposure
+ history. Reset-crossing pairs excluded (within-life evolution only).

| Dimension | Test n | Ridge MAE (mm) | Ridge RMSE (mm) | Ridge R2 | Persist MAE (mm) | Persist RMSE (mm) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wsmDia | 48,674 | 17.9511 | 20.1675 | -0.913 | 1.8383 | 6.6638 |
| wsmFlangeThickness | 48,655 | 1.0209 | 1.1856 | -2.725 | 0.2640 | 0.6076 |
| wsmRoot | 48,544 | 0.8042 | 1.1059 | 0.001 | 0.6863 | 1.1387 |
| wsmWheelGauge | 48,651 | 0.3319 | 0.4643 | -0.162 | 0.0797 | 0.2347 |

## Reading this

- MAE in mm = error in the NEXT measured value prediction (best accuracy of
  the estimated next wheel state).
- Persistence (predict current state unchanged) is the naive baseline; the
  model should match or beat it while also estimating *direction*.
- R2 / Spearman indicate whether predicted next state tracks the actual next
  measurement (supports prioritization).
- Exposure is duration-based (days), not km: RTIS km semantics blocked.
