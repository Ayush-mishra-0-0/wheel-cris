# Phase 3B - Conformal prediction comparison

Same chronological split (60/20/20 train/calibration/test) for all methods.
Target: 80% coverage.

| Dimension | Method | Coverage | Mean width (mm) | p90 width (mm) | Conformal shift (mm) |
| --- | --- | ---: | ---: | ---: | ---: |
| wsmDia | plain_quantile | 84.5% | 12.257 | 19.946 | 0.000 |
| wsmDia | cqr_quantile | 93.2% | 13.290 | 20.979 | 0.516 |
| wsmDia | cqr_mean | 91.4% | 13.292 | 13.292 | 6.646 |
| wsmFlangeThickness | plain_quantile | 80.1% | 2.982 | 8.274 | 0.000 |
| wsmFlangeThickness | cqr_quantile | 91.1% | 3.193 | 8.485 | 0.106 |
| wsmFlangeThickness | cqr_mean | 84.5% | 3.340 | 3.340 | 1.670 |
| wsmRoot | plain_quantile | 86.5% | 2.520 | 3.175 | 0.000 |
| wsmRoot | cqr_quantile | 93.5% | 2.826 | 3.482 | 0.153 |
| wsmRoot | cqr_mean | 90.8% | 2.892 | 2.892 | 1.446 |

## Reading this

- plain_quantile: honest but no formal guarantee (can be slightly wide).
- cqr_quantile: conformal width added to the quantile band -> guarantees
  ~>=80% coverage distribution-free; watch the width cost.
- cqr_mean: simple symmetric +/- band with a conformal guarantee; widths
  should be compared against the quantile methods.
- If CQR coverage lands near 80% with modest width increase, it is the
  defensible interval for the paper (guarantee + tightness).
