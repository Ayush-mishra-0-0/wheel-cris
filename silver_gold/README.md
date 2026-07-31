# Silver and Gold Pipeline Design

## Objective

Move the project from raw Bronze extraction into a versioned Silver layer for cleaning and a Gold layer for decision-ready datasets.

## Scope for the first implementation slice

1. Create a Silver measurement dataset from the Bronze wheel measurements extract.
2. Standardise business time and identity candidates, preserve raw values, and
   quarantine invalid/duplicate records with explicit quality evidence.
3. Create a deliberately thin Gold candidate view; health/risk features are
   added only after wheel identity and engineering-limit validation.

## Planned architecture

- Bronze: immutable raw parquet snapshots from SQL extraction.
- Silver: cleaned, deduplicated, and quality-flagged business records.
- Gold: curated datasets for engineering questions such as wheel health, maintenance intervals, and abnormal wear.

## Current implementation status

- The wheel-measurement Silver transformation implements contract versioning,
  point-in-time business timestamps, quarantine, plausibility flags, source
  checksums and a run-level quality report.
- A regression test covers the initial measurement cleaning behavior.
- The pipeline writes Parquet outputs into data/silver, data/gold and
  reports/data_quality.

## Next work

- Add more robust cleaning rules for sentinel dates and impossible values.
- Build Silver datasets for maintenance/job-card and operational exposure data.
- Derive Gold tables for wheel asset timelines and health snapshots.
