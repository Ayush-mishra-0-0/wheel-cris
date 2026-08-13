# Phase 3 — Event & Censoring Audit

## Decision

**Do not train a survival model yet.** The recorded turn flag is usable as a candidate maintenance-realization signal, but the duplicate-event rule and censoring mechanism require explicit approval.

## Recorded-event evidence

- 42,492 `wsmturning1` rows reduce to 37,739 distinct equipment-days after same-day deduplication.
- Side-2 agrees on 97.3% of turn-1 rows; disagreement must remain an event-quality flag.
- Consecutive flagged-row gaps are reported in `event_censoring_audit.json`; a cross-day cluster threshold is deliberately not inferred by this audit.

## Observation-window evidence

- Latest source measurement: 2026-07-24. The median equipment observation end is 95 days earlier.
- 81.5% of equipment are last seen more than 30 days before the global end; 23.4% are last seen more than 365 days earlier.

| Horizon | Eligible states | Eligible % | Realized turnings | Event rate |
| ---: | ---: | ---: | ---: | ---: |
| 30 d | 988,734 | 86.6% | 22,751 | 2.301% |
| 90 d | 939,210 | 82.3% | 42,441 | 4.519% |
| 180 d | 826,448 | 72.4% | 71,231 | 8.619% |
| 365 d | 605,499 | 53.1% | 89,993 | 14.863% |

## Required decisions

1. Approve event deduplication: same equipment-day only, or a longer post-turning cluster window with a documented operational basis.
2. Define whether a missing future measurement means administrative end of observation, reassignment/withdrawal, or unknown follow-up.
3. Identify whether replacement/provision events should compete with, censor, or be included in maintenance realization.
4. Approve the minimum event count and follow-up coverage required before each horizon is reported.

## Provisional safe use

Until the decisions above, a rolling binary benchmark may use only fixed-horizon labels with demonstrated follow-up for every negative example. Survival fitting and claims about maintenance RUL remain blocked.
