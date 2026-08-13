# Feature Store v1.0 contract

**Grain:** one released Gold-B inspection interval, keyed by
`operational_exposure_id`. It is a governed training/analytics input, not a
prediction, health score, or decision product.

## Admission rule

The builder reads `configs/engineering_feature_specification_v1.json` and
materialises only features with status `READY`, `READY_WITH_CAVEAT`, or
`READY_FOR_MATERIALISATION`. `PENDING`, `BLOCKED`, and `FUTURE` features are
recorded in `feature_registry.json` as excluded; they cannot appear as columns
in `feature_store_v1.parquet`.

## Required outputs

- `feature_store_v1.parquet`: keys, score boundary, and approved feature values.
- `feature_registry.json`: materialised/excluded feature decisions from the spec.
- `lineage.json`: exact input checksums, version, grain and point-in-time rule.
- `coverage.json`: non-null count and coverage by materialised feature column.
- `feature_quality.json`: row/key integrity and release verdict.
- `feature_catalog_generated.md`: generated human-readable catalog; never edited manually.

## Point-in-time and consumer rules

- The score boundary is `interval_end_timestamp`; no future source fact is
  allowed.
- Feature caveats remain binding. RTIS source events are not proven braking
  mechanisms; job-card creation is not completion; static axle load is not
  dynamic train load; RTIS coverage is not distance.
- Models must select feature columns through `feature_registry.json`, retain
  lineage/version metadata, and exclude identifiers from model inputs unless an
  approved modelling design explicitly permits them.
