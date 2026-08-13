# Safety-limit crossing as a tail-probability problem

**Date:** 2026-08-11 · **Phase 3F** · verdict: the question IS answerable — and for
diameter the answer is "essentially never".

## The question

> Will the dimension cross its safety limit before the next planned intervention
> (~90 days)?

The open-loop `dX` regressor (all of 3E/3F) failed because it predicts the
**conditional mean** of the residual, which is ~0.  The user's argument: the
safety question is a **left-tail** statement,

```
p = P(X_{t+90} < L | state_t) = P(dX_90 < L - X_t | state_t),
```

which is answerable even when `E[dX_90|state] ≈ 0`, provided we model the
crossing event / residual tail directly, with current distance-to-limit as the
dominating feature.  This probe tests exactly that.

## Method

Frozen train/test split, `horizon_window == "90d"` rows only (the next
inspection is ~90d out).  Three models, all point-in-time:

| id | model | idea |
|----|-------|------|
| B0 | unconditional prior | no learning; the "persistence already works" baseline |
| B1 | logistic on **current margin only** | distance-to-limit as sufficient statistic |
| B2 | XGBoost on margin + root/dia/flange/gauge state + lifecycle + days-since-turning + recent rates | geometry/lifecycle conditioning of the tail |

Metrics: AUC, Brier score, ECE (10-bin calibration), decision-value
precision/recall at the top decile.

Limits: root 3.0 mm MAX (approved), dia 1016 mm MIN (owner limit, new ~1096),
flange diagnostic-only.

## Results

### Diameter at the owner safety limit 1016 mm (90d)

| model | test positives | AUC | Brier | ECE |
|-------|:---:|:---:|:---:|:---:|
| B0 prior | 3 / 8,346 | — | 0.00036 | 0.0001 |
| B1 margin-only | 3 / 8,346 | 0.9999 | 0.00035 | 0.0003 |
| B2 XGB full | (not run; <20 events) | — | — | — |

**Answer to the exact question: No — essentially never.**
- Calibrated crossing probability ≈ **0.0004** (0.04%) at 90d.
- p1 current margin to 1016 is **11.6 mm**; wheels are turned at ~1070 mm,
  i.e. ~54 mm of margin remaining — nobody in the fleet approaches 1016.
- The margin-only model still "works" (AUC 0.9999) because the 3 events are
  wheels already sitting at the limit; there is no degradation curve to learn.

### Diameter at operational thresholds (where events actually exist)

| threshold | test positives | AUC | Brier | ECE | recall@top10% |
|-----------|:---:|:---:|:---:|:---:|:---:|
| 1030 mm | 153 | 0.991 | 0.008 | 0.003 | 0.99 |
| 1040 mm | 375 | 0.985 | 0.015 | 0.005 | 0.95 |

The machinery is excellent **when there are events**.  B2 catches 95–99% of
crossers in the top decile and is well calibrated (ECE < 0.005).  The tail is
predictable; the reason 1016 is uninteresting is that the fleet never gets there.

### Root > 3 mm (the safety question that actually bites)

| model | test positives | AUC | Brier | ECE |
|-------|:---:|:---:|:---:|:---:|
| B0 prior | 513 / 8,346 | — | 0.061 | 0.058 |
| B1 margin-only | 513 / 8,346 | 0.855 | 0.054 | 0.048 |
| B2 XGB full | 513 / 8,346 | 0.862 | 0.049 | **0.012** |

Top-decile decision: precision 0.32, **recall 0.52** — half of all root>3 mm
crossings within 90d are caught by flagging the top 10% of wheels by risk.

## What this proves

1. **The user's argument is confirmed.**  A tail-probability model is learnable
   where the mean-residual regressor is not.  Root crossing (>3 mm) is a real
   event with real, well-calibrated predictiveness (ECE 0.012 vs prior 0.058).
2. **Current margin dominates** (B1 alone → AUC 0.855), and geometry/lifecycle
   context **recalibrates** the tail (ECE 0.048 → 0.012) even though it barely
   moves AUC — exactly the "covariates modulate the tail, not the mean" case.
3. **For diameter the answer is a confident "no"** — not because the model is
   weak, but because the fleet turns wheels at ~1070 mm, far above 1016.  The
   safety question for diameter is operationally moot in this population.

## Recommendation

- Replace "will diameter cross 1016?" with **"will root cross 3 mm in 90d?"**
  as the safety-constraint question; a top-decile root-risk flag gives ~52%
  recall at ~32% precision.
- Do **not** add diameter-limit crossing as a production alert: calibrated
  probability is ~0.04% and there is no failure mode to catch.
- The right deployment is a **calibrated classifier on the crossing event**
  (root), not an open-loop degradation regressor.

## Files

- `models/phase3f/run_crossing_tail_probe.py`
- `models/experiments/v3f/dia_crossing_tail_probe.json`
- this report
