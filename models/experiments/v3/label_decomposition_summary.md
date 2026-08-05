# V3 label-decomposition — stage-1 detection + stage-2 wear regression

Eval rows (v1.2 test, sentinel-free): 28,065. Train rows: 144,373.
Large-loss prevalence: train 0.5936 · val 0.6315 · test 0.7154

Model per feature set: stage-1 HGB classifier on `next_interval_large_loss_flag`;
stage-2a HGB on clean intervals (`large_loss_flag==0`); stage-2b HGB on loss
intervals; combined = P*loss_pred + (1-P)*clean_pred. Single-stage HGB on all
intervals is the champion reference. All on the same rows.

## baseline

| component | MAE | RMSE | R² | Spearman | σ_pred/σ_true | ≤±5 | ≤±10 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single-stage | 11.397 | 14.566 | 0.530 | 0.646 | 0.742 | 26.8% | 53.1% | 29.1 |
| combined | 11.451 | 14.665 | 0.524 | 0.637 | 0.725 | 27.1% | 52.8% | 29.5 |
| stage-2a (clean only) | 5.782 | 7.873 | 0.710 | 0.790 | 0.832 | 55.5% | 83.8% | 15.9 |

| stage-1 detection (test) | PR-AUC | ROC-AUC | precision@1000 | ECE | positive_rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.9274 | 0.8523 | 0.9800 | 0.0193 | 0.7154 |

### Conditional bias by magnitude bin (pred − true; positive = over-predict / under-state loss)

| bin | n | single bias | single MAE | combined bias | combined MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| <=-40 | 1717 | -31.68 | 31.68 | -32.37 | 32.37 |
| (-40,-20] | 5469 | -11.33 | 11.68 | -11.86 | 12.07 |
| (-20,-10] | 5570 | +0.85 | 6.07 | +0.44 | 5.71 |
| (-10,0] | 6486 | +7.41 | 10.02 | +7.28 | 9.90 |
| (0,10] | 4159 | +9.75 | 12.27 | +9.81 | 12.26 |
| (10,20] | 1977 | +8.42 | 12.02 | +8.47 | 11.90 |
| (20,40] | 1879 | +7.20 | 9.75 | +7.82 | 10.13 |
| >40 | 808 | +11.63 | 11.94 | +12.34 | 12.62 |

## baseline_plus_distance

| component | MAE | RMSE | R² | Spearman | σ_pred/σ_true | ≤±5 | ≤±10 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single-stage | 11.382 | 14.531 | 0.532 | 0.649 | 0.742 | 26.6% | 53.0% | 29.1 |
| combined | 11.439 | 14.630 | 0.526 | 0.641 | 0.733 | 26.5% | 53.0% | 29.2 |
| stage-2a (clean only) | 5.784 | 7.880 | 0.710 | 0.789 | 0.832 | 55.7% | 83.5% | 16.1 |

| stage-1 detection (test) | PR-AUC | ROC-AUC | precision@1000 | ECE | positive_rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline_plus_distance | 0.9271 | 0.8524 | 0.9800 | 0.0191 | 0.7154 |

### Conditional bias by magnitude bin (pred − true; positive = over-predict / under-state loss)

| bin | n | single bias | single MAE | combined bias | combined MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| <=-40 | 1717 | -31.58 | 31.58 | -32.01 | 32.01 |
| (-40,-20] | 5469 | -11.30 | 11.59 | -11.48 | 11.80 |
| (-20,-10] | 5570 | +0.89 | 6.02 | +0.76 | 5.87 |
| (-10,0] | 6486 | +7.41 | 10.05 | +7.43 | 10.05 |
| (0,10] | 4159 | +9.76 | 12.35 | +9.76 | 12.26 |
| (10,20] | 1977 | +8.40 | 12.09 | +8.55 | 11.93 |
| (20,40] | 1879 | +7.24 | 9.73 | +7.80 | 10.15 |
| >40 | 808 | +11.55 | 11.84 | +12.11 | 12.35 |
