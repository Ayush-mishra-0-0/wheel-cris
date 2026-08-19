# Risk Event Contract v1.1

**Status:** Approved for Phase 4 fixed-horizon risk-ranking benchmark (Track A decision intelligence).
**Owner:** Wheel-Project Data Engineering
**Approval date:** 2026-08-11 (v1.0); 2026-08-19 (v1.1)
**Versioning:** this document is immutable. Any change is a new semantic version, appended
to the changelog, never edited in place.
**Dependencies:**
- `docs/maintenance_event_specification_v1.0.md` (turning event semantics, approved 2026-08-06)
- Event & Censoring Audit v1 (`models/experiments/v3/event_censoring_audit/`)
- Target Eligibility Matrix v1 (`models/experiments/v3/target_eligibility/`)
- `docs/degradation_semantics.md` §3.3 (root = direct defect depth, owner-confirmed Q8)
- `configs/limit_register_v1.json` (APPROVED wear limits, source = **Wrpld table**:
  flange 3.0 / root 6.0 / tread 6.5 mm). **Root condemning value is 6.0 mm; any earlier
  "3 mm root" figure is superseded by Wrpld.**

---

## 1. Purpose and scope

Defines how a wheel inspection at time `t` is turned into a labelled risk observation
for Phase 4. It freezes, for **each** of the six (target × horizon) outcomes, the rules
for:

- eligible observation,
- follow-up window,
- exclusion,
- maintenance / reset handling,
- missing follow-up,
- leakage (point-in-time) rules,
- label assignment.

This is a **label/eligibility contract**. It does not define a model, a health score,
or an engineering margin; those live in the Phase 4 plan and the engineering layer.

## 2. Targets

| Target | Id | Event definition |
| --- | --- | --- |
| Root constraint (engineering risk) | A | `root > 6 mm` strictly inside `(t, t+H]` |
| Turning realization (maintenance) | B | recorded turning (`wsmturning1 == 1`) strictly inside `(t, t+H]` |

Horizons `H` = **30 / 90 / 180 calendar days** (fixed-horizon labels only; survival
is out of scope, §8).

### 2.1 Target A — Root constraint

- **Measurement semantics:** `wsmRoot` is a direct defect-depth measurement on the
  wheel; **6 mm is the maximum / condemning value, lower is better** (Wrpld table,
  `configs/limit_register_v1.json`; this supersedes the earlier 3 mm owner-questionnaire
  value of 2026-08-08). It is **not** a cumulative since-turning index.
- **Direction:** root *grows toward* the limit. Margin `= 6 − root`; negative margin =
  beyond condemning.
- **Point-in-time state:** use the current measurement's valid side(s):
  mean of both valid sides, else the single valid side, else row excluded from
  target-A input (missing root).
- **Event:** any within-horizon inspection whose root **exceeds 6 mm** while the
  wheel remains within its lifecycle (replacement boundaries handled in §5).

### 2.2 Target B — Turning realization

- **Event signal:** `wsmturning1 == 1` only. `wsmturning2` is a **quality flag** and
  never creates or cancels an event.
- **Data source (verified 2026-08-11):** the v3f column `turning_record_at_measurement`
  is all-zero; the turning signal is joined from WES
  (`model_datasets/v3/wheel_engineering_state_v1.0.parquet`,
  `turning_record_at_measurement == 1`, 5,246 events) onto v3f rows via
  `measurement_record_id` (complete in v3f).
- **Event timestamp:** source record update time (`wsmUpdatedOn`) of the first flagged
  row in an event cluster, after equipment-day deduplication (§3).
- **Grain:** one event per **equipment-day**.

## 3. Deduplication (target B)

- Same-day, same-equipment flagged rows collapse to one event on that day; the first
  identical-day flagged row defines the timestamp.
- This is the **only** deduplication authorised. Cross-day "turning campaign"
  aggregation is **not** authorised until an operational basis is approved.
- Repeated flags on different days are distinct events.

## 4. Horizon label rule

For a fixed horizon `H`, an inspection row at `t` is:

```
Eligible = (observation_end − t) >= H  OR  (an event day falls strictly inside (t, t+H])

label(within_H) = 1  if an event day falls strictly inside (t, t+H]
label(within_H) = 0  if eligible and no event falls inside the window
label(within_H) = None (excluded) if the row has neither full follow-up nor an event in-window
```

`observation_end` = per-equipment last measurement record, **never** the global extract
end (Event & Censoring Audit v1).

## 5. Exclusion and maintenance/reset rules

1. No attributable wheelset (`wsmEquipmentId` missing) — excluded.
2. No usable timestamp (`wsmUpdatedOn` missing) — excluded.
3. `Unknown follow-up` for the horizon — excluded from **that horizon's** cohort.
4. **Replacement** (wheel/wheelset provision change) is **not** a turning event. It
   only affects observation end; it never fabricates an event and never fabricates a
   root-constraint crossing.
5. **Turning** (target B) resets the wear clock but does **not** reset the root state
   (root is direct depth, not cumulative — `degradation_semantics.md` §3.3).
6. Rows at a turning boundary are handled as follows: an inspection row **at** `t`
   uses the state measured at that inspection; the event window opens strictly after
   `t`, so a turning flagged **at** `t` does not label itself.
7. Missing root measurement (target A) — row excluded from target-A input for that
   horizon; counted and reported as missingness (never imputed).

## 6. Leakage / point-in-time rules

- **Feature set at `t`:** only information available at the inspection — current state
  (measured dims + quality), history (days since turning, wheel age proxy, lifecycle
  segment, recent 30/90/180d changes/rates), exposure/context (RTIS counts, distance
  where approved), categoricals (shed, position, defect, profile).
- **Forbidden:** any future measurement, event, jobcard, or timestamp; exact-handle
  time fields; replacement/before-`H` flags as predictors (they are targets/censoring
  only, never features).
- **Rolling cutoff:** training uses only observations whose outcome is complete by
  cutoff `T`; scoring uses only states known by `T`. Point-in-time discipline is the
  primary leakage control (Phase 4 plan §7).

## 7. Reporting obligations

Every Phase 4 result must record per (target, horizon):

- prevalence (event rate) on train and test cohorts,
- eligibility and exclusion counts,
- unknown-follow-up count,
- censoring percentage and available follow-up,
- calibration curve / ECE,
- capture@5%, capture@10%, lift, precision@top-k,
- stability by calendar period, shed, wheel/profile type, measurement
  quality/missingness strata.

## 8. Out of scope

- **Survival (time-to-event) modelling — blocked.** See Event & Censoring Audit
  decision and `maintenance_event_specification_v1.0` §8.
- Censoring-mechanism informativity — unproven; not assumed non-informative.
- Diameter 1016 mm crossing and flange-limit crossing — semantic gates; **not**
  Phase 4 benchmark targets (pending owner confirmation).
- Continuous diameter-ΔX regression — closed by Phase 3F.

## 9. Changelog

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-11 | 1.0 | Initial risk event contract. Two targets (root>3mm, turning=1) at 30/90/180d; eligibility/exclusion/label rule; point-in-time leakage rules; survival blocked. |
| 2026-08-19 | 1.1 | **Target A retuned from `root > 3 mm` to `root > 6 mm`.** The Wrpld table is now the authoritative wear register (`configs/limit_register_v1.json`): flange 3.0 / root 6.0 / tread 6.5 mm. The earlier 3 mm root figure (Q8, 2026-08-08) is superseded. Margin = `6 − root`. Benchmarks built before this change remain frozen and are labelled with their `limit_root_mm` in the v4 manifest; new runs use 6.0 mm. |
