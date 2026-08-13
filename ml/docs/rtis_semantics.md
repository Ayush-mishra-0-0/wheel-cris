# RTIS Mileage Semantics

**Status:** Evidence-based interim contract; source-owner confirmation still
required before distance is used in engineering features.

The complete distance-specific decision and SQL guardrail are maintained in
[`rtis_distance_semantics.md`](rtis_distance_semantics.md).

## Source

`RtisLocoKmDetails` → cohort-filtered Bronze `rtis_mileage.parquet`  
Fields: `RlkdId`, `RlkdLocoNumber`, `RlkdReportDate`, `RlkdDivision`,
`RlkdTotalDistance`, `RlkdSlamEntryDate`.

## What one RTIS row represents

The strongest supported interpretation is:

> One source distance report for a **locomotive, report date, and division**,
> uniquely identified technically by `RlkdId`.

It is **not** safely interpretable as a trip, a unique locomotive-day record,
or a point reading from a lifetime odometer.

Evidence from 4,320,461 WAP7 rows:

- 1,329,555 locomotive-day groups exist.
- 1,007,109 locomotive-days (75.75%) contain multiple divisions.
- Samples contain several distance values for one locomotive on one report date,
  each associated with a different division.
- `RlkdSlamEntryDate` is an ingestion/load timestamp; it may occur later than
  the report date and must not be used as operational event time.

## Is kilometreage cumulative?

**No—the field does not behave as a lifetime cumulative counter.**

If it were cumulative, daily maxima for a locomotive should usually be
monotonic. Instead, across consecutive reported days:

| Change in daily maximum | Count |
| --- | ---: |
| Increased | 651,168 |
| Decreased | 659,464 |
| Unchanged | 16,991 |

The almost balanced increases/decreases, together with sample daily maxima in
the low hundreds of kilometres, rules out a simple pattern such as
`120000 → 120520 → 120760`.

Therefore:

- Do **not** compute distance as a difference between successive
  `RlkdTotalDistance` values.
- Counter-reset and overflow handling are **not applicable** under the current
  interpretation. Reassess only if the RTIS source owner states that the field
  has another meaning.

## Can duplicates exist?

Yes. `RlkdId` is unique, but duplicate **business reports** exist.

Business key used for evidence:

```text
(RlkdLocoNumber, RlkdReportDate, RlkdDivision, RlkdTotalDistance)
```

| Measure | Value |
| --- | ---: |
| Repeated business keys | 121,283 |
| Excess repeated rows | 153,221 |
| Largest repeat count for one key | 166 |

Examples show the same report reloaded minutes or hours apart with different
`RlkdId`/`RlkdSlamEntryDate`. These must not be summed.

## Missing days and continuity

- 93,087 gaps greater than one day occur in locomotive reporting sequences.
- The largest observed gap is 546 days.
- A gap can mean no service, no RTIS reporting, an unavailable device, or an
  extraction/source gap. It is not automatically zero distance.

No daily distance-continuity assumption is permitted until the source owner
confirms the business process and coverage expectations.

## Safe interim handling

1. Preserve every Bronze row unchanged.
2. In Silver, retain `RlkdId` and expose a duplicate-business-key flag.
3. For any exploratory daily view, keep at most one record per exact business
   key, choosing the latest `RlkdSlamEntryDate`; retain both original count and
   deduplication flag.
4. Do **not** sum division values to create daily distance and do **not**
   difference values across dates.
5. Do **not** attach interval kilometres, wear/km, distance-since-turning, or
   exposure scores to Gold intervals yet.
6. Use only structural/contextual fields (presence, division coverage, report
   dates) as auditable operational evidence until confirmed.

## Required source-owner questions

1. Is `RlkdTotalDistance` distance travelled in that division on that report
   date, a daily total, a trip value, or another aggregation?
2. May different division rows for the same loco/date be summed? If yes, how
   should repeated rows be resolved?
3. What causes repeated business reports and which record is authoritative?
4. Does an absent report imply zero running, unavailable RTIS, or missing data?
5. What timezone and cut-off define `RlkdReportDate`?

## Release decision

**RTIS event context: PASS WITH LIMITATIONS.**  
**RTIS interval distance / distance-based features: BLOCKED** until the five
questions above are answered and the aggregation contract is approved.

## Reproducible evidence

- `sql/validation/rtis_mileage_semantics_profile.sql`
- `sql/validation/rtis_semantics_deep_profile.sql`
- `sql/validation/rtis_semantics_samples.sql`
- `sql/validation/rtis_duplicate_pattern.sql`
- `sql/validation/rtis_duplicate_samples.sql`
