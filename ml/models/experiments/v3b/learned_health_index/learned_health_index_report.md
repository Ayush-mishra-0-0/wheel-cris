# Phase 3B - Learned Health Index

Research-grade upgrade: the 0-100 health score is LEARNED from the 90-day
maintenance-risk model and calibrated (isotonic) on a held-out chronological
period, so a score carries a probability meaning.

- Test-period metrics: PR-AUC 0.3422, ROC-AUC 0.8764, Brier 0.0307 (pre) -> 0.0291 (post-calibration).
- Latest wheels scored: 19,167; median learned health 99.32.

| risk bucket | wheels |
| --- | ---: |
| LOW_RISK | 14,598 |
| MEDIUM_RISK | 3,348 |
| ELEVATED_RISK | 612 |
| HIGH_RISK | 609 |

## Why this is better than the rule-based index

- Weights come from data (which feature combos actually precede turning),
  not hand-set 0.5/0.5.
- Calibrated: health 40 ~= 60% probability of turning within 90 days.
- Same features as the benchmark, so the number is reproducible.
- Both indexes coexist: rule-based (transparent v1) + learned (empirical v2).
