# RTIS Distance Semantics and Aggregation Rule

**Status:** technical grain resolved; physical distance aggregation is **not approved**.  
**Decision:** `RTIS_DISTANCE_FEATURE_STATUS = BLOCKED`

## Executive decision

`RlkdTotalDistance` is not a locomotive lifetime cumulative counter. It also
cannot safely be summed across all reports for a locomotive/day. No database
metadata, stored routine, or extended-property documentation defines the field's
physical business meaning.

Until the RTIS source owner approves an aggregation rule, do not calculate:

```text
interval kilometres, wear/km, distance-since-turning, exposure index,
or distance-based ML features.
```

## Raw grain

One raw row is a unique technical report (`RlkdId`) containing locomotive,
report date, division, reported distance and SLAM load time. The supported
technical grain is:

```text
(locomotive, report date, division, report instance)
```

It is not one trip, one unique locomotive-day record, or an odometer reading.
`RlkdSlamEntryDate` is a load/audit timestamp, not movement time.

## Cumulative versus incremental

The field is **not cumulative**. Across consecutive reported days, a
locomotive's daily maximum increased 651,168 times and decreased 659,464 times.
A lifetime counter should be near-monotonic.

It is also **not proven to be daily incremental distance**. On 2023-03-22,
locomotive 37170 has latest reports of 61.39 km (BSB), 2,285.59 km (DLI),
618.44 km (PRYJ) and 2,181.52 km (TVC). Their same-date total is 5,146.94 km,
which is physically implausible for daily locomotive travel.

## Multiple rows and duplicates

- 1,329,555 locomotive-day groups exist.
- 1,007,109 (75.75%) contain multiple divisions.
- Division reporting is therefore material to the grain.

Repeated business reports exist under this key:

```text
(loco number, report date, division, reported distance)
```

| Measure | Value |
| --- | ---: |
| Repeated business keys | 121,283 |
| Excess repeated rows | 153,221 |
| Maximum reports for one key | 166 |

Samples show identical reports loaded minutes/hours later with new `RlkdId`.
These are re-ingested reports and must not be summed.

## Candidate aggregation rules tested

| Candidate | Maximum loco-day total | Decision |
| --- | ---: | --- |
| Raw sum of all rows | 7,918.30 km | Rejected |
| Exact business-key dedupe then sum | 5,154.62 km | Rejected |
| Latest report per loco/date/division then sum | 5,146.94 km | Rejected |

No database-only aggregation rule represents trustworthy physical travel.

## Missing days, reset and overflow

- 93,087 reporting gaps exceed one day; the maximum gap is 546 days.
- Absence may mean no service, unavailable RTIS, reporting delay, or source
  loss; it must not become zero km.
- Counter reset/overflow logic is not applicable because this is not a lifetime
  counter.

## SQL implementation rule

### Approved now

Preserve all Bronze rows. In Silver, flag repeated reports with:

```sql
PARTITION BY RlkdLocoNumber, CAST(RlkdReportDate AS date),
             RlkdDivision, RlkdTotalDistance
```

`duplicate_rtis_business_report` is retained as an accepted-with-flag state.

### Prohibited now

```sql
SUM(RlkdTotalDistance)
LAG(RlkdTotalDistance) / difference
SUM(...) BETWEEN inspection timestamps
```

## Required source-owner sign-off

1. Definition/unit of `RlkdTotalDistance`.
2. Period represented by `RlkdReportDate`.
3. Whether division reports are independent and additive.
4. Authority rule for reloaded/duplicate reports.
5. Meaning of absent reports and expected cadence.
6. Timezone/cut-off of report date.

After approval, implement exactly the owner-approved rule—either a deduplicated
division sum, an authoritative report selection, a defined counter difference,
or a different trip/position source.

## Reproducible evidence

- `sql/validation/rtis_semantics_deep_profile.sql`
- `sql/validation/rtis_distance_aggregation_candidates.sql`
- `sql/validation/rtis_distance_aggregation_samples.sql`
- `sql/validation/rtis_duplicate_pattern.sql`
- `sql/validation/rtis_distance_metadata_search.sql`
