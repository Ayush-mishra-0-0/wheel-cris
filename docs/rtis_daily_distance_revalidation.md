# RTIS daily-distance revalidation

## New domain evidence

A senior domain review states that `RlkdTotalDistance` is sensor-derived
movement data and that values below 10 km can occur when a locomotive is in a
shed, stabled, or moves only minimally. This is important evidence supporting a
daily movement interpretation, but it does not by itself approve the SQL
aggregation across multiple report/division rows.

## Shed cross-check: locomotive 30201

The reproducible query
`sql/validation/rtis_idle_shed_crosscheck_30201.sql` groups RTIS values by
locomotive/report day, identifies consecutive blocks below 10 km, and checks
overlap with `foisshedin`/`foisshedout` records.

- 37 low-km blocks of at least 3 days were identified.
- 15 blocks have overlapping FOIS shed evidence.
- The available shed history for this locomotive begins on 2024-05-22 and ends
  on 2026-07-28; therefore earlier unmatched blocks have **no shed-source
  coverage**, not evidence of being outside a shed.
- Later unmatched blocks remain unclassified: they may be stabling, incomplete
  shed records, or another operational state.

## Current status

`RlkdTotalDistance` is upgraded from “rejected interpretation” to
**PENDING DAILY-AGGREGATION VALIDATION**. It remains blocked from Feature Store
distance features until all release checks pass.

## Fleet-level corroboration

The same rule was run across the WAP7 cohort by
`sql/validation/rtis_idle_shed_crosscheck_wap7_summary.sql`:

- 29,229 low-km blocks of at least three consecutive days were found across
  1,936 locomotives.
- 15,540 blocks overlap a FOIS shed record, involving 1,927 locomotives.
- 13,689 blocks have no overlapping shed record **or no shed-history coverage**.

This is strong corroboration that low daily RTIS kilometres often occur during
shed presence, but it is not a claim that every low-km block is a shed event.

## Remaining release checks

1. RTIS owner confirms one raw row’s grain and whether division rows are
   distinct additive sensor segments, overlapping reports, or reloads.
2. Validate the proposed daily aggregation across a representative locomotive
   sample against FOIS shed in/out evidence and known locomotive movement.
3. Quantify duplicate/reload handling and physically implausible daily totals
   after the approved rule.
4. Define coverage semantics: no RTIS report and no FOIS shed record must never
   become zero movement or “not in shed”.
5. Version the approved SQL rule, tests, and a quality report before changing
   `interval_distance_km` from BLOCKED.
