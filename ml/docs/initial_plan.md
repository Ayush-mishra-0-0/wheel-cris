# Railway Wheel Intelligence: Agreed Direction and Plan

## Assessment

I agree with the assessment's central conclusion: the project should not be
framed as a narrow "predict the next wheel measurement" exercise. The Bronze
and future Gold layers can support a decision-support product for wheel health,
maintenance planning, fleet comparison, and route/operating-condition analysis.

The strongest defensible formulation is:

> Estimate wheel health and future degradation, identify **likely contributing
> factors**, and recommend the next engineering investigation or maintenance
> action.

This is deliberately not a claim to prove that a particular subsystem caused a
failure. The available historical data is observational, so it can establish
associations and prioritise inspections—not diagnose a faulty bearing,
suspension, brake, or alignment without direct condition-monitoring evidence.

## Strategic position

The project is feasible with the core data already identified. The principal
bottleneck is now **domain-data acquisition and integration**, not model
selection. The durable asset is an engineering-grade data model and feature
store that reconstructs wheel life; individual ML algorithms can evolve without
redesigning that foundation.

Core feasibility questions already answered:

| Question | Status |
| --- | --- |
| Can we identify and longitudinally track a wheel/equipment item? | Yes, subject to the planned identity and effective-date validation. |
| Can we reconstruct inspection and maintenance history? | Yes. |
| Can we map wheel/equipment to locomotive? | Yes; the `LocoEquipments` bridge is available. |
| Can we calculate operational exposure? | Yes, from detailed RTIS mileage and emergency-event data. |
| Can we create maintenance/failure context? | Yes, from job cards and defect history. |
| Can we define RUL-style targets? | Yes, after agreeing the intervention/failure endpoint and censoring rules. |

This does not mean every feature is production-ready today. It means the
foundation is sufficient to start building useful engineering intelligence now.

## Delivery levels

We will proceed in four levels. Each level remains valuable on its own; ML is
not a prerequisite for operational value.

| Level | Purpose | Deliverables |
| --- | --- | --- |
| 1. Engineering Truth | **What happened?** Only time-stamped, attributable facts. | Measurement, turning/replacement, maintenance, defect/failure, locomotive assignment, RTIS distance/event and location records. |
| 2. Engineering Intelligence | Derive reproducible engineering signals from Level 1. | Wear rate/acceleration, health and exposure indices, distance since turning, maintenance interval, data-quality and risk rules. |
| 3. Decision Intelligence | Answer actionable questions with rules, trends, cohorts and comparisons. | Turn/inspect priority, abnormal locomotive list, maintenance effectiveness, shed/fleet comparisons, evidence-led investigation prompts. |
| 4. Learning System | Improve forecasts and prioritisation from labelled history. | Regression/classification/survival/RUL, physics-informed models, continual learning and a calibrated digital twin. |

Every fact and derived signal must be traceable to source records. Level 4 can
never override that engineering evidence; it augments it with predictions and
uncertainty.

## Delivery phases

The levels describe *how* the product matures; these phases describe *what is
built next*. They overlap where a source becomes available, but the sequence
protects the project from waiting for optional data.

| Phase | Focus | Principal outputs |
| --- | --- | --- |
| 1. Engineering Timeline | Reconstruct the factual life of every wheel. | Equipment/wheel identity, installation/assignment, inspections, turning/replacement, maintenance, defects, and attributable RTIS distance/events. |
| 2. Decision Intelligence | Turn the timeline into explainable engineering action without requiring ML. | Current health, wear trend/rate, maintenance interval, risk rules, abnormal-wear and maintenance-priority views. |
| 3. Context Enrichment | Add operating context at inspection-interval grain. | RTIS/FOIS exposure, external weather, train/load proxies, route/track enrichment and coverage/confidence flags. |
| 4. Physics-informed Intelligence | Translate context into engineering severity features and evaluate predictive models. | Wear budget, contact/route severity proxies, exposure index, interpretable risk and RUL models. |
| 5. Digital Twin | Continuously update the wheel state and learn from outcomes. | Per-wheel live profile, online refresh, outcome feedback, sensor fusion and controlled continual learning. |

## Current implementation track

### Track A — Data Engineering (highest priority)

The pipeline continues whether or not enrichment data arrives. The required
sequence is Bronze → Silver → Engineering Layer → Gold Feature Store, with
reproducible runs, source lineage, point-in-time correctness and quality gates
at every transition.

Initial implementation order:

1. Produce cohort-filtered raw RTIS mileage and emergency-event extracts.
2. Build the canonical Silver wheel-measurement dataset at source-record grain;
   retain raw fields, standardise business timestamps and identity candidates,
   quarantine invalid records, and emit a versioned quality report.
3. Validate the `wheel -> equipment -> locomotive` identity path and its
   effective dates before claiming a wheel-level timeline.
4. Add Silver maintenance, defects, RTIS mileage and emergency-event datasets
   under the same contract/lineage framework.
5. Build point-in-time inspection intervals and the Engineering Layer.
6. Publish decision-ready Gold products with feature definitions and coverage
   flags—not anonymous table dumps.

### Implementation status (2026-07-27)

- Configured WAP7 cohort materialised: 2,317 locomotives.
- Bronze RTIS mileage extract completed: 4,320,461 cohort-filtered records for
  the configured date window.
- Bronze RTIS emergency extract completed: 783 cohort-filtered records.
- Silver `wheel_measurements` v1.0.0 completed from 1,165,641 Bronze records,
  with source checksum, record-level flags and a quarantine dataset.
- Silver `rtis_mileage` v1.0.0 completed from all 4,320,461 extracted RTIS
  records; all passed the initial structural checks.
- The next non-negotiable gate is validation of the effective-dated
  `wheel -> equipment -> locomotive` assignment before constructing an actual
  wheel-level timeline or inspection-to-inspection exposure interval.

### Critical validation milestone

Temporal identity validation is the release gate for the Engineering Layer.
This is a temporal join—not a static ownership lookup: every measurement must
map to the locomotive assignment valid at its measurement time. The evidence
pack in [`validation/`](validation/README.md) must establish identity,
cardinality, provision/removal-date semantics, assignment overlap and
point-in-time coverage before the Wheel Timeline or engineering features are
trusted.

Initial validation shows `LocoEquipments` has one row per equipment ID rather
than an observed assignment history, and 9.30% of its rows lack a valid
provision date. It is therefore a current/provisioned association—not yet a
complete temporal ledger. The Wheel Timeline remains gated on point-in-time
coverage and a defensible transfer/removal-history solution.

`LocoEquipmentsHistory` is the candidate transfer/removal ledger: it covers
97.44% of measured equipment IDs and supplies provision/removed dates. Under
the first explicit interval rule, 77.95% of evaluated measurements have exactly
one valid assignment interval; 1.10% are ambiguous and 20.95% unmatched. The
first Wheel Timeline may proceed only for the exactly-one-interval subset, with
all other records carrying an auditable exclusion reason.

### Track C — Engineering Intelligence (starts immediately)

1. **Wheel timeline:** inspection → maintenance → distance → inspection.
2. **Health features:** diameter loss, wear rate/acceleration, days and
   distance since turning, maintenance and inspection interval.
3. **Health rules:** remaining diameter, threshold crossing, explainable health
   and risk scores.
4. **Gold products:** Wheel Health Card, Wheel Timeline, Maintenance Timeline,
   Fleet Dashboard and Maintenance Dashboard.
5. **ML:** regression, classification, survival/RUL and physics-informed
   models only after the factual and engineered layers are validated.

The acquisition/research register is maintained in
[`docs/research_backlog.md`](docs/research_backlog.md) so incomplete enrichment
work remains owned and visible without stalling this track.

## Core requirements vs value multipliers

### Required foundation

These make the first engineering and decision capabilities possible:

- persistent wheel/equipment identity and wheel-to-locomotive assignment;
- dated wheel measurements and intervention history;
- maintenance and defect/failure history;
- RTIS mileage/events, linked to locomotive and time.

### Version-1 enrichment targets

We will maximise the use of these sources in Version 1 wherever coverage,
meaning and point-in-time linkage pass validation. They are not a reason to
delay the core timeline, but they are explicit V1 workstreams—not deferred
ideas:

- FOIS route/location and train context when WAP7 coverage is available;
- externally enriched historical weather;
- authoritative track curvature, gradient, track quality and rail profile;
- static locomotive axle load plus train/load context and a validated load
  index; and
- all currently available condition signals (for example wayside bearing/event
  alerts), followed by richer suspension, brake-pressure, wheel-slip and
  vibration sensors as they become available.

The data model must provide a versioned, optional feature interface for every
enrichment. A missing enrichment must produce a coverage flag—not an invented
or silently imputed physical exposure.

## What the current data supports

The Bronze layer already provides a strong base:

| Evidence | Current value |
| --- | --- |
| Wheel measurement history | 1.17M rows; geometry, wear, wheelset position, turning indicators, and timestamps |
| Maintenance/job-card history | 4.43M rows; locomotive key, work remarks, and event timestamps |
| Equipment register | 2.66M rows; enables the wheel -> equipment -> locomotive identity path |
| Defect history | 376,660 rows; potential failure/maintenance context |
| Locomotive/cohort data | WAP7 cohort and locomotive/type lookup available |

### Operational-source verification (SQL Server, 2026-07-27)

The detailed event data is available in SQL Server. It has been discovered and
validated; what remains is to engineer it into point-in-time intervals aligned
to wheel inspections.

| Source | Detailed fields confirmed | WAP7 direct-match evidence | Readiness |
| --- | --- | --- | --- |
| `RtisLocoKmDetails` | locomotive number, report date, total distance | 5,390,971 of 17,404,571 rows; 1,940 cohort locomotives; 2023-02-06 to 2026-07-25 | Ready for mileage/exposure engineering |
| `INTEG_rtisLocoEmergencyData` | locomotive, event/time, kilometreage, latitude/longitude, speed, station/division | 783 of 3,276 rows; 501 cohort locomotives; 2023-09-15 to 2025-03-29 | Ready for event feature engineering, subject to event-code semantics |
| `FOIS_LocoLocation_History` | loco number, FOIS/RTIS station/division, reporting/event time, load/rake IDs, latitude/longitude | 0 direct matches using `LocoMaster.LomNumber = LocoNumb` | Raw events exist; identifier reconciliation is required before use |

The verified raw operational data is therefore a major project asset, not
unusable metadata. The key missing product is the interval feature:

```text
inspection at t0 -> operational events between t0 and t1 -> inspection at t1
                   -> distance, trip count, speed behaviour,
                      emergency-event count, spatial/route exposure
```

RTIS coverage begins in 2023, so operational-feature models must be trained and
evaluated within their observed overlap with the wheel timeline. Earlier wheel
history remains valuable for health and maintenance models but must not be
treated as having unobserved RTIS exposure.

Track geometry and quantitative train load remain unverified. Weather can be
added as external contextual enrichment because the operational sources provide
latitude/longitude and station/division/time fields; it is a supporting
feature, not primary evidence of wheel degradation. Direct sensor signals such
as vibration, brake pressure, wheel-slip ratio and subsystem-condition data are
later-phase inputs for more specific diagnostics.

## Eight-domain readiness audit (SQL Server and Bronze, 2026-07-27)

The eight domains below are the complete target feature framework. **Green**
means sufficient to build Level 1 facts and begin derived signals; **amber**
means a source exists but needs extraction, reconciliation, semantics, or a
quality gate; **red** means no suitable source has yet been identified.

| Domain | Evidence found | Readiness | What can proceed / what is missing |
| --- | --- | --- | --- |
| 1. Wheel health | 1.17M `WheelSetMeasurements` records with measurement dates, diameter, flange, root/tread-related, gauge, skid and turning fields. | Green | Build the canonical measurement timeline and health rules after unit/range validation. |
| 2. Wheel history | Prior-measurement fields, dated measurement history, turning flags, equipment register, and job cards. | Green | Compute inspection deltas, wear rate and time since turning. Validate replacement/turning semantics. |
| 3. Locomotive behaviour | RTIS mileage has 5.39M WAP7-linked events; emergency events expose time, kilometreage, speed, location and event type. | Amber | Build distance, event-count and speed features. Confirm event-type meaning and whether speed is representative; no direct wheel-slip/brake-pressure signal confirmed. |
| 4. Route behaviour | FOIS detailed station/division/time/coordinate fields reconcile to the full locomotive master at 99.34% of distinct identifiers (99.37% after leading-zero normalisation). RTIS has station/division/location fields. | Amber | The current FOIS location-history extract contains no WAP-family records, so it cannot enrich the WAP7 V1 cohort today. This is a coverage gap—not an identifier mismatch. Use RTIS location context now; obtain WAP7 FOIS coverage or an alternative movement source for route reconstruction. No track-geometry/curve/gradient reference has been identified. |
| 5. Operational load | `LocoTypes` provides static class configuration: WAP7 has `LotWeight = 123`, `LotNumberOfAxels = 6`, and `LotAxelLoad = 20.5`. FOIS has `LoadID`/`RakeID`; defects include partial load/wagon/train fields; `INTEG_icmsLocoTrainAttachmentDetail` confirms loco, attachment date and train/station fields. | Amber | Static locomotive axle load is available for V1. No verified time-varying hauled-train weight/axle-load field has been found; validate joins and use a documented train/load index when supported. `LoadID` alone is not a usable load value. |
| 6. Environment | RTIS/FOIS expose location and time; no weather source exists inside the current SQL Server catalogue. | Amber | Enrich event intervals through a weather API/archive using latitude/longitude (or a validated station geocode) and event time. Record provider, retrieval time, spatial/temporal resolution and missingness; use only as a supporting contextual feature. |
| 7. Failure history | 376,660 defect-history rows with occurrence time, locomotive, section, defect/failure codes, equipment context and action text. | Green | Build failure/defect timelines and maintenance-outcome labels after code and text-category validation. |
| 8. Mechanical configuration | Equipment register (2.66M records), locomotive master/type data, and a confirmed effective-dated `LocoEquipments` bridge (`LoeLocoMaster`, `LoeEquipmentMasterRegister`, provision date); bogie/suspension lookup tables exist. | Amber | Wheel/equipment-to-locomotive linkage can be built. Verify historical deprovision/replacement logic and whether the bogie/suspension lookups contain per-locomotive fitted configuration. |

**Decision:** We are ready to move ahead with Levels 1 and 2 immediately, and
with Level 3 for health, abnormal-wear, maintenance and fleet decisions. The
principal external-data dependency is authoritative track geometry—especially
curvature and gradient—mapped to the route/segment locations actually travelled.
Weather enrichment can be added once event locations are standardised. Exact
subsystem-driver diagnosis is a later, sensor-enabled phase.

## Target product and model sequence

```text
Verified source data
        -> Silver canonical timelines
        -> Engineering knowledge layer
        -> Gold decision-ready marts / feature store
        -> Health + abnormal-wear detection
        -> Likely-driver explanations
        -> RUL / maintenance-risk prediction
        -> Prioritised engineering action
```

Health assessment should come first: it establishes trustworthy current state
and targets. Driver analysis should then explain observed abnormal degradation;
RUL uses both the health state and the validated exposure/history features.

Initial outputs for engineers:

1. **Wheel health and risk score** — current geometry against validated limits,
   wear rate, confidence, and threshold proximity.
2. **Abnormal-wear alert** — wheels wearing faster than comparable wheels,
   adjusted for available age, locomotive, and maintenance context.
3. **Likely contributors** — grouped as wheel history, maintenance,
   locomotive, operation, route, and environment; state association and
   uncertainty, never certainty of cause.
4. **Maintenance recommendation** — inspect, monitor, reprofile/turn, or
   schedule review, tied to a reason and a prediction horizon.
5. **Fleet and route views** — only once exposure data is complete enough to
   compare locomotives/routes fairly.

## Gold layer organised around engineering questions

Create Gold datasets by decision, rather than mirroring source tables:

- `wheel_asset_timeline`: each wheel/equipment's inspections, maintenance,
  defects, locomotive assignment, replacement/turning events, and data-quality
  flags.
- `wheel_health_snapshot`: latest valid measurements, derived wear measures,
  limits, health/risk status, and confidence.
- `wheel_exposure_interval`: interval between inspections with distance,
  emergency/braking, route, load, and weather exposure where available.
- `maintenance_effectiveness`: condition before/after work and time/distance to
  the next intervention.
- `loco_wheel_health_summary`: comparable wheel-health and abnormal-wear rates
  by locomotive/type, adjusted for known exposure.
- `route_wheel_exposure_summary`: route/segment comparisons only after route
  identity and geometry coverage are verified.

## Engineering feature groups

Build versioned features with definitions, units, source lineage, validity
rules, and leakage checks.

- **Wheel health:** diameter, flange thickness, root/tread-related fields,
  wheel gauge, skid/turning state, position, and quality flags.
- **Wheel history:** time since prior inspection, change from prior valid
  inspection, wear rate, wear acceleration, turning/reprofiling count and depth
  where derivable, and time since turning.
- **Maintenance and defects:** job-card timing/text categories, recurring work,
  defect categories, and time since relevant event.
- **Locomotive context:** locomotive type, age/configuration where populated,
  repeated wheel-level abnormality across replacement cycles.
- **Operational exposure:** RTIS interval mileage, distance/day, speed,
  kilometreage, emergency-event counts/types, station/division, trip count and
  time in service. FOIS route, location and load/rake fields follow after a
  WAP7-containing source is obtained. Gradients and curve exposure follow after
  a track-geometry reference is acquired.

## Immediate next steps

### 1. Complete and validate the data pipeline

1. Inventory every Bronze dataset as **raw events**, **profile-only**, or
   **reference/metadata**; record grain, timestamp, key, coverage, refresh
   date, and known quality problems.
2. Build incremental, cohort-filtered Bronze extracts for `RtisLocoKmDetails`
   and `INTEG_rtisLocoEmergencyData`. Partition by report/event date and retain
   source identifiers, timestamps, and raw values.
3. Reconcile `FOIS_LocoLocation_History.LocoNumb` to `LocoMaster.LomNumber`.
   First profile normalisation candidates (spaces, leading zeroes, prefixes,
   numeric/text representation); if this fails, find the cross-system mapping
   rather than forcing a join. The current direct match rate is 0/63,817 rows.
4. Validate the identity path in production data:
   `wheel measurement.wsmEquipmentId -> equipment register.EmrId -> locomotive`.
   Measure match rates, multiplicity, and effective dates before joining.
5. Define and implement Silver cleaning rules for sentinel dates (for example
   `1900-01-01`), impossible values, duplicate business events, units, and
   measurement plausibility. Preserve raw values and emit rejection/quality
   flags rather than silently dropping records.
6. Confirm the meaning and engineering limits/units of each wheel measurement
   field with a domain owner before deriving health labels.

### 2. Define the first decision questions and labels

1. Hold a short engineer workshop and rank 10--15 questions by action value,
   data availability, and measurable success; later expand to the 30--50
   question catalogue.
2. Choose one initial target with reliable historical labels, preferably
   **abnormally high wear rate / threshold crossing within a fixed horizon**.
3. Define each outcome precisely: wheel identity/grain, observation time,
   horizon, censoring, intervention/turning handling, and acceptable action.
4. Establish baselines: last-observation, age/mileage trend, and cohort/group
   comparison before more complex ML.

### 3. Build the first engineering and Gold slice

1. Implement `wheel_asset_timeline` and `wheel_health_snapshot` first.
2. Derive validated prior-measurement deltas and wear rates without using future
   measurements (point-in-time correctness).
3. Create a data-quality dashboard/report: join coverage, temporal coverage,
   missingness, outlier rates, and samples of each Gold record's lineage.
4. Build RTIS inspection intervals now; add FOIS route/location enrichment
   after WAP7 movement coverage is obtained.

### 4. Model and evaluate responsibly

1. Start with health rules and abnormal-wear detection; provide the raw
   evidence alongside any score.
2. Train an interpretable tabular baseline for the selected horizon with
   time-based and locomotive/wheel-grouped splits to prevent leakage.
3. Report calibration, recall at the maintenance-review capacity, lead time,
   false alerts, and performance by locomotive class/shed/time period.
4. Use feature attribution as a *model explanation*, aggregate it into
   engineering categories, and phrase results as "likely contributors".
5. Validate alert usefulness with engineers through reviewed cases before
   presenting recommendations as operational guidance.

## Decision gates

Do not proceed to the corresponding claim until its gate is passed:

| Claim / capability | Required gate |
| --- | --- |
| Wheel-level longitudinal health | Stable wheel identity, timestamp ordering, and valid measurement ranges |
| Wear rate per distance | Valid consecutive measurements plus attributed mileage for the same interval |
| Emergency braking as a driver | Event-level RTIS emergency records with locomotive/time match and sufficient coverage |
| Route/curve/gradient driver | Movement-to-route/segment linkage plus verified track geometry |
| Specific subsystem diagnosis | Later-phase direct sensor and maintenance evidence (for example vibration, brake pressure, wheel-slip, bearing/traction/suspension signals) linked to loco/time; until then, only recommend investigation |
| RUL | Clear failure/intervention endpoint, censoring policy, enough follow-up, and a decision horizon |

## Ambitious build path

1. **Operational wheel digital twin:** for every wheel/equipment timeline,
   continuously refresh current health, elapsed distance, events, maintenance,
   predicted degradation, uncertainty, and recommended next action.
2. **Shed morning risk board:** rank wheels/locomotives by a capacity-aware
   maintenance risk score, giving evidence and an investigation checklist.
3. **Fleet intelligence:** identify locomotives with repeated abnormal wear
   across multiple wheel cycles after adjusting for available exposure and
   maintenance context.
4. **Network intelligence:** after FOIS reconciliation and track enrichment,
   compare route/segment exposure and flag locations needing infrastructure
   review. Treat this as a screening signal, not proof of a track defect.
5. **Learning system:** log engineer reviews and maintenance outcomes, then use
   them to validate, recalibrate, and improve the features and recommendations.

## External enrichment strategy

### Weather (supporting context)

1. Standardise RTIS/FOIS coordinates and timestamps; geocode stations only
   where coordinates are absent or invalid.
2. Select a documented weather API or historical archive with appropriate
   spatial and temporal resolution.
3. Retrieve precipitation, temperature and humidity for each operational
   interval; cache the response and retain source/version metadata for
   reproducibility.
4. Evaluate weather only as an incremental feature over the operational and
   maintenance baseline. Do not interpret an association as evidence that
   weather caused wear.

### Track geometry and gradient (principal gap)

The required source must provide, at minimum, a stable **line/route or track
segment identifier**, kilometre/post or spatial geometry, gradient, and curve
attributes (radius/degree or a defensible curvature class). It must be mappable
to the station/coordinate trajectory from RTIS/FOIS and have an effective date
or version. Preferred acquisition order:

1. Authoritative railway infrastructure/track-geometry records from the
   responsible engineering organisation (Track Engineering, Civil Engineering,
   Permanent Way/P-Way or a track-management-system owner). Seek track ID,
   chainage, curve radius, gradient, rail section, turnouts, restrictions and
   track-quality/maintenance history where available.
2. Official GIS/asset inventory with kilometre posts and route/section mapping.
3. GIS/route-map data that can map route, chainage and coordinates; elevation
   can support exploratory gradient reconstruction only after engineering
   validation.
4. A validated external/open reference (for example OpenStreetMap or
   OpenRailwayMap) for exploratory research enrichment—not maintenance
   recommendations—until reviewed by railway engineers.

Do not create synthetic curve or gradient values from station names alone.
Every exposure feature must preserve source, mapping confidence and coverage.

### Load context

Use the static `LocoTypes.LotAxelLoad` configuration (WAP7: 20.5; validate unit
with engineering) as a V1 mechanical-load feature. It is not a substitute for
the time-varying load of the hauled train. Join locomotive, attachment time and
train identifier to wagon/rake information where available. If a defensible
mapping to wagon count/type or train category is established, expose a
documented ordinal `load_index` (for example low/medium/high) rather than
pretending it is an exact dynamic axle load. The mapping, coverage and
uncertainty must remain visible.

## Guardrails

- Keep Bronze immutable; make all Silver/Gold transformations reproducible and
  versioned.
- Separate data availability from data usefulness: a populated field can still
  be unreliable or unavailable at prediction time.
- Prevent target leakage: every feature must be known at the score timestamp.
- Treat turning/reprofiling and wheel replacement as state-changing events,
  not ordinary observations.
- Preserve uncertainty and missing-exposure flags in every score.
- Do not promise causal findings from correlations; use causal language only
  with a documented causal design and appropriate assumptions.

## Near-term definition of success

Within the next implementation cycle, success is a validated, point-in-time
wheel timeline and health snapshot for the WAP7 cohort, a documented first
decision target, and an audited baseline alert/risk model. That is the
foundation for a useful engineering system; RUL, fleet intelligence, and route
analytics can then be added with evidence rather than assumptions.

## Current business-truth milestone

Produce a validated, point-in-time Gold-B equipment/wheelset timeline with
lineage, temporal-integrity checks and an explicit Gold-C exclusion dataset.
Only that Gold-B subset may feed inspection-interval construction; all other
records remain available for audit and systematic coverage recovery.

### Gold-B timeline build (2026-07-27)

The first WAP7 cohort timeline has been materialised under the timeline
contract. Of 319,707 measurements in the WAP7 history candidate universe,
271,350 (84.87%) have exactly one valid assignment interval and are Gold B.
The remaining 48,357 are Gold C: 45,211 have no valid interval and 3,146 have
multiple intervals. The 821,575 full-fleet measurements outside the WAP7
history universe are reported separately, not misclassified as WAP7 exclusions.

The output remains an equipment/wheelset-candidate timeline until
`wsmEquipmentId` business semantics are validated. It is eligible for the next
step—inspection-interval construction—but not yet for engineering features or
ML.

### Inspection intervals v1.0 (2026-07-27)

Business Truth v1.0 is frozen as the baseline for interval construction. From
252,183 consecutive Gold-B measurement pairs, 225,262 (89.33%) are Gold-B
intervals with the same locomotive and positive duration. The 26,921 Gold-C
interval exclusions are retained for audit: 20,229 non-positive-duration pairs
and 6,692 locomotive changes between consecutive inspections. RTIS,
maintenance and other exposure are the next enrichment layer; engineering wear
rates and ML remain gated on interval sanity validation.

### Engineering Truth Validation gate (2026-07-28)

The formal evidence pack is [engineering_truth_validation.md](validation/engineering_truth_validation.md).
Its verdict is **PASS WITH KNOWN LIMITATIONS**: Business Truth and interval
boundaries are released for enrichment, but RTIS distance aggregation, wear
interpretation, health scoring, RUL and ML remain blocked pending approved
business rules and RTIS distance semantics.

RTIS semantics evidence now establishes that `RlkdTotalDistance` is not a
lifetime cumulative counter and that duplicate business reports exist. The
interim contract is [rtis_semantics.md](docs/rtis_semantics.md): retain RTIS
context and coverage, but block interval kilometres and all distance-based
engineering features until the source owner approves an aggregation rule.

The formal distance decision is
[rtis_distance_semantics.md](docs/rtis_distance_semantics.md). Database tests
reject raw, exact-deduplicated, and latest-division daily sums as physically
implausible; no physical-distance aggregation rule is released.

### RTIS daily-distance revalidation (2026-07-29)

Senior domain review now confirms that `RlkdTotalDistance` is sensor-derived
movement data and that sub-10 km reports can correspond to shed/stabling or
minimal movement. A direct cross-check for locomotive 30201 found 15 of 37
consecutive low-km blocks overlapping FOIS shed evidence. The FOIS shed history
only begins on 2024-05-22, so earlier unmatched blocks are coverage gaps—not
counter-evidence.

The fleet-level cross-check found 15,540 shed-overlapping low-km blocks among
29,229 WAP7 blocks (at least three days), across 1,927 locomotives. The
remaining blocks are explicitly retained as “no shed evidence or coverage,”
not classified as outside a shed.

This makes RTIS daily kilometreage a **pending validation candidate**, but it
does not yet release it: the RTIS owner must still approve the meaning of
multiple division rows and the daily aggregation/deduplication rule. The full
release checklist is [rtis_daily_distance_revalidation.md](docs/rtis_daily_distance_revalidation.md).

### Distance-source recovery lookup (2026-07-28)

A read-only SQL Server catalogue and data search found `MovementRegister` and
`RTISLOCOKM` as potential alternatives. Neither is releasable today.
`MovementRegister` has 452,973 WAP7 records across 2,309 locomotives and
includes speedometer and mileage fields, but raw values exhibit billion-scale
outliers, negative increments, and 57,127 continuity breaks. `RTISLOCOKM` has
no direct WAP7 matches. The detailed evidence and an owner-led recovery plan
are in [distance_recovery_plan.md](docs/distance_recovery_plan.md). The
preferred path remains RTIS-owner confirmation; Movement Register semantics
and WAP-covered FOIS movement data are parallel investigations, not substitutes
to be assumed valid.

### Distance alternatives ranking (2026-07-29)

The alternatives have now been tested. `MovementRegister` is **not** a viable
fleet-distance ledger: most of its WAP7 records are null-status or explicitly
`Under Maintenance`, with only 274 `In Use` records, alongside meter outliers
and broken continuity. The requested `INTEG_FOIS_LocoLocation` table currently
has zero rows, so its latitude/longitude cannot be used.

The best usable operational source is instead
`view_locolocation_trackhistory`: 15,577,312 WAP7 station/time records across
2,272 locomotives. It is released only for ordered location/route context.
It has no route length or coordinates, so railway kilometres remain blocked
until an authoritative station-to-track/chainage network is acquired. Haversine
distance from a future populated GPS feed would be a labelled geodesic estimate,
not rail distance. See [distance_recovery_plan.md](docs/distance_recovery_plan.md).

### IR Geoportal track-data acquisition (2026-07-29)

IR Geoportal is now the preferred official candidate for station reference,
track-network/chainage, curvature, gradient and track-condition data. No public
download, API or station-distance layer could be verified from the portal
surface, so no attributes are assumed available. The exact requested datasets,
fields and FOIS-station integration rule are documented in
[ir_geoportal_acquisition_plan.md](docs/ir_geoportal_acquisition_plan.md).

### Operational Exposure v1.0 (2026-07-28)

The released Gold dataset is
[`inspection_interval_operational_exposure.parquet`](data/gold/operational_exposure/v1.0/inspection_interval_operational_exposure.parquet),
with its immutable-input quality report at
[`operational_exposure_1f73323d-0772-4d4b-bcc4-ea5b12b300ea.json`](reports/data_quality/operational_exposure_1f73323d-0772-4d4b-bcc4-ea5b12b300ea.json).
It has one record for each of the 225,262 eligible inspection intervals and
separates three things by contract:

- verified timestamped source-event and job-card-creation counts;
- provisional RTIS reporting/duplicate/coverage metadata; and
- blocked physical distance, retained as null with
  `BLOCKED_PENDING_SOURCE_CONFIRMATION` on every record.

The materialisation contains 2,234 intervals with RTIS source events, 161,551
with job-card creation events, and 134,866 with RTIS reports; 90,396 have no
RTIS report inside the interval. Absence of a report is a coverage condition,
not evidence of zero movement. The contract is in
[operational_exposure_contract.md](configs/operational_exposure_contract.md),
and the live delivery/research release register is
[feature_readiness_catalog.md](docs/feature_readiness_catalog.md).

### Engineering Feature Specification v1.0 (2026-07-28)

Priority 3 is complete as a governed, machine-readable contract rather than a
static feature list. The source of truth is
[`engineering_feature_specification_v1.json`](configs/engineering_feature_specification_v1.json),
with a JSON Schema and CI validator. It defines 14 actual/planned features,
including their formula, unit, Engineering Layer owner, point-in-time
availability, lineage, validation rules, dependencies, readiness and explicit
consumer limits. It prevents a blocked feature from being quietly
materialised.

The product hierarchy is now Business Truth, Inspection Intervals, Operational
Exposure, Engineering Features, Feature Store, Wheel Health Snapshot, Fleet
Health and Decision Products. “Gold” remains the technical storage tier, not a
catch-all product name. The next delivery is Health Index design using only
features that this specification permits.

### Feature Store v1.0 (2026-07-28)

Feature Store v1.0 is released under
[`feature_store/`](feature_store/). Its builder reads the feature specification
directly and admits only `READY`, `READY_WITH_CAVEAT` and
`READY_FOR_MATERIALISATION` features. The released interval-grain dataset has
225,262 unique records, 7 approved feature definitions and 7 explicitly
excluded definitions (4 blocked, 2 pending, 1 future). `interval_distance_km`
is demonstrably excluded.

The store emits a feature registry, input-checksum lineage, per-column coverage,
quality verdict and generated catalog from the same JSON specification. This is
the only permitted route from engineering features to a future training dataset;
models must not read raw Bronze/Silver or blocked feature values.

## Layered Engineering Intelligence architecture

The platform architecture is frozen as an **Engineering Intelligence Platform**,
not a premature Digital Twin. The layer contract, source mapping, output
boundaries, extension principles and future Twin design are in
[engineering_intelligence_platform.md](docs/architecture/engineering_intelligence_platform.md).
Only Identity, State evidence and Behaviour interval boundaries are currently
released. Exposure is partial; Degradation, Health, Prediction and Decision
remain deliberately blocked until their inputs and validation gates are met.
