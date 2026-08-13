# Dataset Card — model dataset v1.2

- **Parent:** v1.1 (immutable; X matrix + split assignment identical for retained rows)
- **Rows (supervised):** 202,172  (was 202,237; 65 quarantined)
- **Features (X):** 96 (unchanged from v1.1)
- **Label spec:** 1.0.1 — quarantine rule `physical_endpoint_diameter_window`
- **Quarantine rule:** wsmDia1 of `interval_end_measurement_id` OR `next_interval_end_measurement_id` outside [1000, 1100] mm
- **Quarantined by split:** train 55 · val 9 · test 1
- **Split rows:** train=144,373 · val=29,734 · test=28,065
- **max |next_interval_dia_delta_mm| after quarantine:** 80.30 mm

## Why

Label spec 1.0.0 retained physically-impossible label endpoints (bronze wsmDia1 values of 0 and >1e6 mm), producing |delta| labels up to ~1090 mm. These carry ~30% of total regression MSE and poison the training target distribution. Label spec 1.0.1 adds a deterministic quarantine rule (patch bump, per Continuous Evolution Guide section 2). See `models/experiments/v1.2/sentinel_audit_findings.md`.

## Provenance

- `parent_dataset_version`: v1.1
- `feature_store_version`: 1.0.0
- `feature_spec_version`: 1.0.0
- `label_spec_version`: 1.0.1
- Generated: 2026-08-04T08:41:34.796602+00:00
