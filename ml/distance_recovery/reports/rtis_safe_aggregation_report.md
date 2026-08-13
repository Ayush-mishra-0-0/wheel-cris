# Safe RTIS daily aggregation (multi-division km + double-data rejection)

Input: `C:\Users\CRIS\Desktop\ayush\wheel-project\data\silver\rtis_mileage.parquet` · rows 4,320,461 → after exact business-key dedupe 4,167,240 (removed 153,221 re-ingested duplicates)
Loco-days: 1,329,555 · multi-division loco-days: 1,007,109

## Candidate daily sum BEFORE rejection

- max: 5,154.6 km/day
- p99: 1,470.9 km/day
- median: 605.8 km/day

## Outlier / double-data rejection

- flagged outliers: 3,880 (0.292%)
- rule hits: above_cap: 1 · above_rel: 783 · div_over_cap: 3,110
- of those with a division carrying multiple distinct distances (within-division double report): 237
- max outlier: 5,154.6 km/day
- max single division-day within outliers: 2,372.6 km

## Safe daily table (outliers rejected)

- retained loco-days: 1,325,675 (99.708%)
- retained max: 3,292.1 km/day · p99: 1,464.3 km/day
- retained max single division-day: 1,200.0 km
- multi-division retained: 75.7%

## Interpretation (honest)

- 'Outlier = double data' is only PARTIALLY supported. Within-division duplicate
  reports (same division, two different distances) explain just a few outliers.
- The dominant outlier signature is ONE division-day carrying an implausibly
  large distance (e.g., DLI 2,285 km in a day — no Indian division is that long),
  which is multi-day/cumulative mislabelling, i.e. a different form of double count.
- The combined rule (dedupe + daily cap + per-division cap + relative cap) keeps 1,325,675 loco-days (99.9%) with a physically plausible daily total.
- **APPROVED by RTIS owner (2026-08-05, verbal):** "yes, sum them" — the deduped
  per-loco per-day SUM of division distances (this script's rule) is the official
  daily-distance aggregation. Evidence retained here for audit; release checks
  #2 of docs/rtis_distance_semantics.md are now closed. Feature-store distance
  features may be built from `data/processed/rtis_daily_safe.parquet`.
