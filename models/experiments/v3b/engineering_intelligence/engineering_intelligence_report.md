# Phase 3B - Engineering Intelligence

From the frozen Wheel Engineering State v1.0, per-state intelligence for
maintenance prioritisation under incomplete observability.

## Health index and action distribution

- States: 271,350; latest-per-wheel: 19,167; sheds: 32
- Median health index: 72.8/100

| recommended action | states |
| --- | ---: |
| PLAN_TURNING_REPROFILING | 224,699 |
| SCHEDULE_INSPECTION | 44,137 |
| MONITOR | 2,146 |
| URGENT_ACTION | 368 |

## Limiting dimension (the corrective focus)

| limiting dimension | states |
| --- | ---: |
| wsmWheelGauge | 233,166 |
| wsmRoot | 38,184 |

## Method & honesty

- Wear rates are **segment-level** (mm/day over a wheel's current life-segment
  between resets), which averages out the per-inspection noise that dominated
  short-interval next-state prediction.
- Estimated RUL (days) is **rate-based and fleet-relative** toward the documented
  reference thresholds. It is NOT a claim against an approved condemning limit,
  which remains BLOCKED.
- Health index is transparent and rule-based (proximity to reference + wear rate
  + maintenance history), not a black-box scalar.
- Outputs: `engineering_intelligence.parquet`, fleet/shed dashboards, top-priority
  wheel health cards.
