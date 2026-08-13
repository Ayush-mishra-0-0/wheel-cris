# Business Truth Layer v1.0 Release

**Status:** Frozen baseline for interval construction.

## Artifact

- Gold-B point-in-time equipment/wheelset-candidate timeline:
  `data/gold/business_truth/v1.0/wheel_timeline_gold_b.parquet`
- Gold-C timeline exclusions:
  `data/gold/business_truth/v1.0/wheel_timeline_gold_c_exclusions.parquet`
- Quality/lineage report:
  `reports/data_quality/wheel_timeline_7d0c2d85-73c9-4ab5-99c9-a6f9ebc9d138.json`

## Scope

This is a WAP7, equipment/wheelset-candidate truth layer. It is not a claim of
individual physical-wheel identity. Only exactly-one-assignment-interval rows
are Gold B. Rebuilds that change business rules or input snapshots require a
new Business Truth version.
