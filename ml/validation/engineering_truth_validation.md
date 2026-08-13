# Engineering Truth Validation

**Release assessed:** Business Truth v1.0 and Inspection Intervals v1.0  
**Assessment date:** 2026-07-28  
**Verdict:** **PASS WITH KNOWN LIMITATIONS**

The validated Gold-B interval dataset is approved for the next enrichment and
engineering-validation work. It is not yet approved for distance-based wear
features, health scoring, RUL labels, or ML training.

## Evidence inputs

- `data/gold/business_truth/v1.0/wheel_timeline_gold_b.parquet`
- `data/gold/inspection_intervals/v1.0/inspection_intervals_gold_b.parquet`
- `reports/data_quality/engineering_truth_validation_12becebf-cb3b-44ff-8823-badcff54649e.json`
- `reports/data_quality/maintenance_interval_validation_7275a6c5-4f51-4a46-a436-a1e2b646fda2.json`
- `sql/validation/rtis_mileage_semantics_profile.sql`
- `sql/validation/rtis_emergency_integrity.sql`

## Temporal Integrity

| Check | Result | Status |
| --- | ---: | --- |
| Positive interval duration | 225,262 / 225,262 Gold-B intervals; 0 non-positive | Pass |
| Same locomotive at endpoints | 225,262 / 225,262; 0 mismatch | Pass |
| Duplicate interval endpoint pair | 0 | Pass |
| Consecutive inspection construction | 252,183 ordered candidate pairs; created with next inspection by equipment/wheelset candidate and timestamp | Pass |
| Point-in-time assignment validity | 271,350 of 319,707 WAP7 candidate measurements (84.87%) have exactly one assignment interval | Pass |
| Ambiguous assignment intervals | 3,146 Gold-C records (1.10% of the earlier full validation denominator); excluded | Pass with limitation |
| No valid assignment interval | 45,211 WAP7 Gold-C records; excluded | Pass with limitation |

Assignment overlap is not ignored: any measurement with multiple valid history
intervals is Gold C and cannot enter the timeline or interval dataset.

## Measurement Integrity

| Check | Result | Status |
| --- | ---: | --- |
| Diameter endpoint availability | 225,262 / 225,262 for both diameter fields | Pass |
| Flange endpoint availability | 225,245 / 225,262 for both flange fields; 17 missing | Pass with limitation |
| Diameter increase detection | 13,549 (`Dia1`) and 13,601 (`Dia2`) positive raw deltas | Detected; rule pending |
| Flange increase detection | 64,829 (`Flange1`) and 65,049 (`Flange2`) positive raw deltas | Detected; rule pending |
| Impossible wear classification | Not released | Blocked |
| Duplicate inspections | 0 duplicate interval endpoint pairs | Pass |

Positive and negative geometry deltas are retained as raw observations. They are
not labelled as wear or error until engineering approves units, measurement
repeatability, turning/reprofiling semantics, and acceptable change rules.

## Operational Integrity

| Check | Result | Status |
| --- | ---: | --- |
| RTIS mileage structural quality | 4,320,461 WAP7 Bronze/Silver rows; initial Silver structural checks accepted all rows | Pass |
| Negative summed RTIS loco-day distance | 0 / 1,329,555 loco-days | Pass |
| RTIS duplicate source event ID | 0 in the Silver RTIS quality report | Pass |
| RTIS aggregation semantics | 1,007,109 loco-days have multiple divisions; maximum daily summed value is 7,918.3 km | Blocked |
| RTIS distance continuity / interval distance | Not calculated | Blocked |
| Emergency-event uniqueness | 783 WAP7 events; 0 duplicate `IrledId`; 0 missing transmission time | Pass |

`RlkdTotalDistance` must not yet be summed across divisions or attached as
interval distance. Its business grain/cumulative behaviour needs source-owner
confirmation and a documented aggregation rule.

The detailed interim contract and evidence are in
[`docs/rtis_semantics.md`](../docs/rtis_semantics.md).

## Maintenance Integrity

| Check | Result | Status |
| --- | ---: | --- |
| Job-card timestamp availability | 4,429,700 job cards have valid locomotive ID and creation timestamp | Pass |
| Maintenance event inside interval | 161,551 / 225,262 intervals contain at least one job-card creation event | Pass with limitation |
| Multiple maintenance events | 155,560 intervals; maximum 604 | Observed; classification pending |
| Turning before inspection | Not validated | Blocked |

Maintenance presence uses `start < SejCreatedOn <= end`. `SejCreatedOn` is an
available creation time, not confirmed maintenance completion time; it is not
yet an effectiveness label. Turning indicators likewise require engineering
interpretation before use.

## Known limitations and required closure

1. Confirm `wsmEquipmentId` semantics before calling the dataset
   individual-wheel level.
2. Approve geometry units, limits, turning/reprofiling and change-direction
   rules before deriving wear or health features.
3. Confirm RTIS `RlkdTotalDistance` grain and valid daily/interval aggregation
   before distance, wear-per-km, exposure or route metrics.
4. Confirm whether job-card creation, issue or return timestamps represent the
   intended maintenance event time for each use case.
5. Investigate Gold-C assignment gaps and ambiguity without weakening the
   Gold-B eligibility rule.

## Engineering Layer Release Gate

**PASS WITH KNOWN LIMITATIONS.**

Allowed now:

- preserve and enrich Gold-B intervals with auditable event presence/counts;
- investigate and document raw geometry change distributions;
- build data-quality and coverage products.

Blocked until the listed rules are approved:

- wear rate, wear per km/day, health index, maintenance-effectiveness claims;
- RTIS distance/exposure aggregation;
- RUL labels, ML training and predictive decisions.
