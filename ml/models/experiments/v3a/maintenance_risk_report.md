# Phase 3A - Maintenance Risk Benchmark

Question: does engineering state predict maintenance realization better than
chance, and what fraction of future turning events are captured by inspecting
the highest-risk wheels?

Split: temporal 80/20 by measurement time. PR-AUC primary (rare events).
Baseline PR-AUC (random) = test positive rate.

## Results

| Horizon | Model | Test n | Pos rate | PR-AUC | ROC-AUC | R@1% | R@5% | R@10% | P@5% | Brier |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 d | logistic | 48,821 | 0.015 | 0.1100 | 0.8660 | 0.110 | 0.434 | 0.610 | 0.132 | 0.0607 |
| 30 d | randomforest | 48,821 | 0.015 | 0.1253 | 0.8683 | 0.129 | 0.354 | 0.625 | 0.107 | 0.0347 |
| 30 d | xgboost | 48,821 | 0.015 | 0.1638 | 0.8842 | 0.166 | 0.482 | 0.683 | 0.146 | 0.0139 |
| 30 d | catboost | 48,821 | 0.015 | 0.1383 | 0.8626 | 0.156 | 0.410 | 0.637 | 0.124 | 0.0140 |
| 90 d | logistic | 46,152 | 0.038 | 0.2531 | 0.8512 | 0.115 | 0.407 | 0.636 | 0.308 | 0.0715 |
| 90 d | randomforest | 46,152 | 0.038 | 0.2539 | 0.8569 | 0.119 | 0.333 | 0.583 | 0.252 | 0.0548 |
| 90 d | xgboost | 46,152 | 0.038 | 0.3640 | 0.8730 | 0.156 | 0.480 | 0.665 | 0.363 | 0.0302 |
| 90 d | catboost | 46,152 | 0.038 | 0.3550 | 0.8523 | 0.159 | 0.451 | 0.655 | 0.341 | 0.0302 |
| 180 d | logistic | 40,579 | 0.093 | 0.4135 | 0.8381 | 0.061 | 0.292 | 0.526 | 0.541 | 0.0987 |
| 180 d | randomforest | 40,579 | 0.093 | 0.4315 | 0.8356 | 0.088 | 0.276 | 0.465 | 0.510 | 0.0850 |
| 180 d | xgboost | 40,579 | 0.093 | 0.5423 | 0.8643 | 0.096 | 0.346 | 0.572 | 0.640 | 0.0621 |
| 180 d | catboost | 40,579 | 0.093 | 0.5313 | 0.8426 | 0.098 | 0.345 | 0.559 | 0.638 | 0.0614 |
| 365 d | logistic | 29,369 | 0.272 | 0.7464 | 0.8552 | 0.034 | 0.170 | 0.324 | 0.927 | 0.1314 |
| 365 d | randomforest | 29,369 | 0.272 | 0.7107 | 0.8344 | 0.035 | 0.165 | 0.309 | 0.898 | 0.1311 |
| 365 d | xgboost | 29,369 | 0.272 | 0.7746 | 0.8698 | 0.036 | 0.173 | 0.331 | 0.941 | 0.1407 |
| 365 d | catboost | 29,369 | 0.272 | 0.7564 | 0.8513 | 0.036 | 0.171 | 0.329 | 0.929 | 0.1402 |

## Reading Recall@Top-k (Event Capture)

- Recall@Top-5% = if engineers inspect the highest-risk 5% of wheels, the
  fraction of future turning events those wheels contain.
- Random expectation = positive rate (so R@5% should beat ~0.05 for 90d).
- Precision@Top-5% = fraction of the inspected 5% that actually turn, a
  direct measure of inspection workload value.

## Deterministic caveats

- Prediction is of **maintenance realization** under partial observability
  (inspections, RTIS exposure, FOIS movement observed; true trigger, workshop
  batching, capacity, operator judgement unobserved).
- It does not claim to recover the latent engineering decision process.
- 365d has the weakest follow-up (see Target Eligibility Matrix), so its
  numbers are least comparable.
