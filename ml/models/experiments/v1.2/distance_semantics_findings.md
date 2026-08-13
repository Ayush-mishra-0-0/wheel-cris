# RTIS `RlkdTotalDistance` semantics — evidence-based verdict

Source: `data/bronze/rtis_mileage.parquet` (4,320,461 rows, 1,932 WAP7 locos, 949 days).
Tests in `models/rtis_distance_semantics_test.py`, `..._deep.py`, `..._daily_total_test.py`.

## Verdict

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| **Cumulative odometer** | ❌ REJECTED | 49.3% of day-steps the daily max *decreases*; max single-day drop 2371 km; 49.1% of (loco,division) day-deltas negative. A lifetime counter is near-monotonic. |
| **Corrected total** | ❌ REJECTED | Same wild swings (deltas ±65 km median, ±658 p99) — far beyond "corrections". No smooth accumulation base. |
| **Trip / segment distance** | ✅ BEST FIT | Per-(loco,division) series is a sawtooth: 27.4% of day-steps drop >50 km; values jump to a new magnitude each report; repeated values cluster at route lengths (e.g. loco 30201/AGRA pinned ~189 km for many days; 0.0–2.4 km idle cluster). |
| **Daily total (as a sum)** | ⚠️ PARTIAL — only as an aggregate | Per-row is NOT a day total (3.81 divisions/day on average; a single division can carry 90% of the day). But the **deduped per-loco-day SUM is physically realistic**. |

## The one number that matters

Per-loco-day **sum after exact-key dedupe** (loco + date + division + distance):

- median **606 km/day**, p10 1 → p90 1,172 km
- **68.7% of days land in 200–1,200 km** — the realistic WAP7 single-day band
- only 0.02% of days exceed 2,000 km (raw, without dedupe, max was 7,918 km)

Cumulative sum for one busy loco (30201, 760 report days) = ~330k km over the period —
consistent with fleet-scale annual usage, NOT a per-row odometer.

## What this means

1. `RlkdTotalDistance` is best described as **the distance a locomotive covered within
   the reporting division for that report** — a per-division trip/segment reading
   (sensor-derived; values <10 km = shed/stabled, corroborated by the FOIS shed
   cross-check). It is **not** a locomotive-lifetime odometer.
2. A defensible **daily-distance reconstruction** exists: exact-key dedupe, then sum
   across divisions per loco-day. This is the owner-approval-able rule to propose.
3. Duplicates are a *reporting* artifact (re-ingested rows with new `RlkdId`), not
   evidence against the field — dedupe handles them (153,221 excess rows removed).

## Practical path for the V2 experiment (before the data-team nod)

Build an **experimental** interval feature, clearly flagged:
`interval_distance_km_experimental` = deduped RTIS distance summed over reports with
`interval_start <= RlkdReportDate < interval_end` (plus a `rtis_distance_coverage_days`
denominator so a missing report ≠ 0 km). Treat it as experimental — the docs keep
`interval_distance_km` BLOCKED until the owner signs off the grain/aggregation — but
run the v2 ablation to see whether distance-derived exposure moves predictions at all.
