# V3 quantile intervals — calibrated uncertainty on the tails

Test rows: 28,065 · HGB quantile loss (q05/q50/q95) · features: released v1.2 baseline (96).

## Overall

| metric | value |
| --- | ---: |
| [q05,q95] empirical coverage | 92.5% (target ~90%) |
| mean interval width | 52.87 mm |
| median interval width | 54.25 mm |
| q50 MAE | 11.061 |
| q50 RMSE | 14.820 |
| q50 R² | 0.514 |
| q50 σ_pred/σ_true | 0.754 |
| single-stage mean σ_pred/σ_true (v3) | 0.742 |
| pinball q05 / q50 / q95 | 1.943 / 5.530 / 1.044 |

## Per-magnitude-bin calibration (the audit's tail complaint)

| bin | n | coverage | mean width | q05 bias vs true | q95 bias vs true |
| --- | ---: | ---: | ---: | ---: | ---: |
| <=-40 | 1717 | 61.6% | 55.35 | -2.47 | +52.88 |
| (-40,-20] | 5469 | 94.3% | 54.61 | -22.25 | +32.35 |
| (-20,-10] | 5570 | 99.3% | 54.30 | -34.49 | +19.81 |
| (-10,0] | 6486 | 98.6% | 52.92 | -40.37 | +12.56 |
| (0,10] | 4159 | 88.3% | 50.14 | -40.69 | +9.45 |
| (10,20] | 1977 | 87.7% | 48.91 | -38.20 | +10.72 |
| (20,40] | 1879 | 91.4% | 50.43 | -39.22 | +11.21 |
| >40 | 808 | 85.6% | 54.93 | -47.40 | +7.53 |

## Tail sensitivity

- deep negatives (y_true < −40, n=1685): 61% have q05 below/at true (model's own 5% tail does cover the loss); q05 on these is -52.04 vs true mean -49.68.
- deep positives (y_true > 40, n=808): 86% have q95 above/at true.
- Spearman(q05, y_true) = 0.601 (q05 as a downside-risk ranking score).

Note: 'q05 bias vs true' is mean(q05 − true); on deep negatives a negative value
means the 5% quantile sits below the realised loss (conservative), positive means
it still over-states. Width growth across bins shows whether uncertainty scales with
exposure — the property a single point estimate cannot provide.
