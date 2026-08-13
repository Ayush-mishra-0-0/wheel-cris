# V1.3 Rolling Temporal (Production Simulation) Evaluation — v1.2 (cleaned)

Protocol: at each cutoff T, train on all intervals whose next inspection already occurred (next_interval_end <= T) and evaluate on wheels whose next inspection is still pending (interval_end <= T < next_interval_end) — the exact predictions a deployed model issues at T. Champion model: HistGradientBoosting. Dataset: v1.2 (label spec 1.0.1, sentinels quarantined).

## regression · next_interval_dia_delta_mm (RMSE, lower=better)

| cutoff | n_train | n_eval | RMSE | MAE |
| --- | ---: | ---: | ---: | ---: |
| 2016-11-27 | 530 | 1,246 | 30.531 | 25.373 |
| 2018-02-14 | 1,415 | 1,871 | 29.673 | 25.889 |
| 2019-05-04 | 3,856 | 1,973 | 32.147 | 28.643 |
| 2020-07-22 | 9,853 | 1,580 | 36.349 | 33.871 |
| 2021-10-09 | 22,486 | 1,792 | 29.640 | 26.768 |
| 2022-12-28 | 32,815 | 4,607 | 25.721 | 21.655 |
| 2024-03-16 | 50,922 | 8,273 | 22.413 | 18.502 |
| 2025-06-04 | 105,535 | 11,041 | 23.431 | 19.481 |

Median rolling RMSE: **29.657** mm. Grouped-split test RMSE (same v1.2 rows, HGB): **14.566** mm.

> **Honest read — the production scenario is harder than the holdout split.** Rolling RMSE
> is ~1.5–2× the grouped-split test RMSE. The eval set is not a random sample: at each cutoff
> it holds only wheels whose next inspection is still pending (std 28.2 mm vs 21.3 in the
> grouped test, higher turning rate 2.0% vs 1.1%), and the model must extrapolate to recent
> wear without ever having seen the future. R² at the last cutoff is 0.31 vs 0.50 on the
> grouped test — real signal, but the deployment distribution is genuinely harder.
>
> **What still transfers (the important part):** against the **v1.0 rolling baseline at the
> same cutoff (2025-06-04), RMSE improved 33.08 → 23.43 (−29%)**. The v1.1 feature + v1.2
> label-cleanup gains hold under the production protocol — they do not evaporate. Early
> cutoffs are additionally inflated by tiny training sets (530 rows in 2016).

## binary · next_interval_large_loss_flag (PR-AUC, higher=better)

| cutoff | n_train | n_eval | PR-AUC | ROC-AUC | precision@2000 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2016-11-27 | 530 | 1,246 | 0.856 | 0.724 | 0.7424 |
| 2018-02-14 | 1,415 | 1,871 | 0.870 | 0.772 | 0.6713 |
| 2019-05-04 | 3,856 | 1,973 | 0.888 | 0.733 | 0.7471 |
| 2020-07-22 | 9,853 | 1,580 | 0.785 | 0.750 | 0.5747 |
| 2021-10-09 | 22,486 | 1,792 | 0.832 | 0.777 | 0.6071 |
| 2022-12-28 | 32,815 | 4,607 | 0.830 | 0.787 | 0.7875 |
| 2024-03-16 | 50,922 | 8,273 | 0.845 | 0.812 | 0.893 |
| 2025-06-04 | 105,535 | 11,041 | 0.883 | 0.774 | 0.95 |

Binary large-loss transfers strongly: PR-AUC **0.883** rolling (2025-06-04) vs **0.927**
grouped-split test — small degradation, and precision@2000 = 0.95 means ~19 of every 20
flagged wheels actually show material loss. vs the v1.0 rolling baseline at the same
cutoff (PR-AUC 0.801), the champion is +0.082.
