# Rolling stability - maintenance risk (90d, XGBoost)

Robustness of the headline capture result across time cutoffs: each row is a
model trained on data before the cutoff and tested on the following 10% window.

| cutoff | test n | pos rate | PR-AUC | ROC-AUC | R@1% | R@5% | R@10% | Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-02-24 | 22,828 | 0.024 | 0.2498 | 0.8843 | 0.145 | 0.450 | 0.597 | 0.0214 |
| 2025-06-05 | 23,172 | 0.024 | 0.3032 | 0.9214 | 0.219 | 0.486 | 0.715 | 0.0200 |
| 2025-08-23 | 23,034 | 0.027 | 0.3859 | 0.9556 | 0.164 | 0.659 | 0.881 | 0.0209 |
| 2025-11-12 | 22,841 | 0.023 | 0.4919 | 0.9490 | 0.292 | 0.676 | 0.817 | 0.0159 |

## Stability band (mean +/- SD across cutoffs)

- pr_auc: 0.3577 +/- 0.0914 (min 0.2498, max 0.4919)
- roc_auc: 0.9276 +/- 0.0281 (min 0.8843, max 0.9556)
- recall_top_1pct: 0.2048 +/- 0.0572 (min 0.1447, max 0.2920)
- recall_top_5pct: 0.5677 +/- 0.1006 (min 0.4503, max 0.6756)
- recall_top_10pct: 0.7523 +/- 0.1075 (min 0.5967, max 0.8806)
- brier: 0.0195 +/- 0.0022 (min 0.0159, max 0.0214)

## Interpretation

- A tight band around Recall@Top-5% (~48%) means the capture claim is robust,
  not a lucky split.
- Wide bands -> flag which periods the model struggles on (e.g. data drift).
