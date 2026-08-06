# Maintenance Event Specification v1.0

**Status:** Approved for the fixed-horizon maintenance-realization benchmark (Level 3, Validated Targets).

- **Owner:** Wheel-Project Data Engineering
- **Approval date:** 2026-08-06
- **Versioning:** this document is immutable. Any change is a new semantic version, appended to the changelog, never edited in place.
- **Dependency:** uses the observation window and event signal already quantified by [Event & Censoring Audit v1](../models/experiments/v3/event_censoring_audit/event_censoring_audit_report.md) and authorised by [Target Eligibility Matrix v1](../models/experiments/v3/target_eligibility/target_eligibility_report.md).

## 1. Purpose and scope

Defines how a *recorded maintenance realisation* is turned into an observation-level
event for the fixed-horizon benchmark. This is a **label/event contract**, separate
from the measurement-state contract. It does not describe a health score, a failure,
or a margin; it describes when a recorded turning/replacement is counted as a
maintenance realisation and when it is not.

## 2. Event definition

An **event** is a recorded turning realisation attributable to a wheelset/equipment.
Only the `wsmturning1 == 1` flag is treated as the primary event signal.
`wsmturning2` remains a **quality flag** and does not independently create or cancel
an event.

### 2.1 Event timestamp

The event timestamp is the source record update time (`wsmUpdatedOn`) of the first
flagged row in an event cluster, after equipment-day deduplication (section 3).

### 2.2 Grain

One event per **equipment-day** for the purposes of the fixed-horizon benchmark.
A cluster of same-day flags on one equipment is one event, not several.

## 3. Deduplication

- **Same-day, same-equipment** flagged rows collapse to a single event on that day.
- The first identical-day flagged row defines the event timestamp.
- This is the **only** deduplication authorised for the benchmark. Aggregating
  multiple cross-day flags (e.g. a "turning campaign" spanning days)
  is **not** authorised until an operational basis is approved.

### 3.1 Repeated flags

Repeated flags for the same equipment on the same day are a single event.
Repeated flags on **different** days are treated as **distinct events** (each
event has its own timestamp). The audit's cross-day gap distribution
(`event_censoring_audit.json` `turn_flag_gap_buckets`) is retained as disclosure,
not as an automatic cluster rule.

## 4. Handling of special cases

| Case | Rule |
| --- | --- |
| Same-day event | One event (see 3). |
| `wsmturning2` disagreeing | Do not cancel the event. Record as an event-quality flag; count the realisation via `wsmturning1`. |
| Reprofiling (turning) | Counted as a maintenance realisation event at its equipment-day. |
| Replacement (wheel/wheelset provision) | A replacement is **not** a turning event in this benchmark. It is treated per the censoring/exclusion rule in section 5. |
| Row with event after measurement | The event may fall within a horizon; that row is labelled by the event rule in section 6. |

### 4.1 Reprofiling handling

Turning (reprofiling) of a wheel is the maintenance realisation of interest. It is
counted at the equipment-day of the first flagged record.

### 4.2 Replacement handling

Replacement/provision events are **not** counted as turning realisations. Because a
replacement can remove a wheelset from observation, replacement handling is governed
by the censoring and exclusion rules below rather than by inventing a failure label.

## 5. Censoring and exclusion

- **Observation end** is the last measurement record seen for the equipment
  (per-equipment observation end), never the global administrative extract end.
  See [Event & Censoring Audit v1](../models/experiments/v3/event_censoring_audit/event_censoring_audit_report.md).
- A row is **excluded** from a horizon cohort when its observation window is shorter
  than the horizon **and** no event was recorded within the horizon (`Unknown
  follow-up`). Such rows have a genuinely unknowable horizon label.
- **Censored (non-event)** rows have a full observed window with no realised event;
  they are labelled a demonstrated non-event and kept in the eligible cohort.
- Replacement handling cannot silently treat a replaced wheel's absence as an event.
  A replacement that ends observation is reflected only through the per-equipment
  observation end; it does not fabricate a turning event.

## 6. Horizon label rule

For a fixed horizon `H`:

```
Eligible row = (observation_end - measurement_time) >= H
                OR  (event recorded within H)

label(within_H) = 1  if an event day falls strictly inside (measurement_time, measurement_time + H]
label(within_H) = 0  if the row is eligible and no event falls inside the window
label(within_H) = None (excluded) if the row has neither full follow-up nor an event in-window
```

This is the tightened cohort definition from the Target Eligibility Matrix.

## 7. Exclusion rules (final list)

1. Rows with no attributable equipment (`wsmEquipmentId` missing) — excluded.
2. Rows with no usable timestamp (`wsmUpdatedOn` missing) — excluded.
3. Rows that are `Unknown follow-up` for the horizon — excluded from that horizon's eligible cohort.
4. Replacement events do **not** create a turning label (section 4.2).
5. No event is created from `wsmturning2` alone (section 2).

## 8. Explicitly out of scope

- Survival (time-to-event) modelling — **blocked**. See Event & Censoring Audit decision.
- Censoring-mechanism informativity — **unproven**; not assumed non-informative.
- Manufacturer engineering margins or maintenance recommendations — out of scope here.

## 9. Changelog / versioning

Changes must be additive and versioned. A proposed change that alters event
timestamps, deduplication, or exclusion would be a **new major version** and must
remediate the Target Eligibility Matrix and any benchmarks derived from it.

---

## Appendix A. Approved decisions

| # | Decision | Value |
| --- | --- | --- |
| D1 | Event signal | `wsmturning1 == 1` |
| D2 | Event granularity | one event per equipment-day |
| D3 | Deduplication | same-day same-equipment collapse; no cross-day clustering |
| D4 | Replacement | not an event; only affects observation end |
| D5 | Observation end | per-equipment last record, not global end |
| D6 | Unknown follow-up | excluded per horizon |
| D7 | Survival | blocked |
