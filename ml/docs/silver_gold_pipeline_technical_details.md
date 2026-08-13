# Silver and Gold Pipeline Technical Design

## Purpose

This document captures the technical approach for improving the Silver and Gold layers of the railway wheel intelligence pipeline. It translates the high-level plan into an implementation roadmap for data engineering work.

## 1. Pipeline architecture

### 1.1 Layer responsibilities

- Bronze: immutable raw extraction snapshots from SQL Server. No cleaning or business logic.
- Silver: cleaned and standardised business records with lineage, quality flags, and canonical keys.
- Gold: decision-ready datasets that answer engineering questions such as wheel health, maintenance priority, and abnormal wear.

### 1.2 Target flow

```text
Bronze parquet files
  -> Silver canonical datasets
  -> Gold analytical marts / feature store
  -> dashboards, rules, and downstream ML features
```

## 2. Initial engineering scope

The first implementation slice should focus on the wheel measurement domain because it is already available in Bronze and is central to wheel-health analysis.

### 2.1 Silver datasets to build first

1. wheel_measurements_silver
   - Standardise measurement timestamps.
   - Flag invalid timestamps and impossible values.
   - Preserve raw values and keep lineage to Bronze.

2. maintenance_silver
   - Standardise job-card and maintenance events.
   - Parse important text fields and attach quality flags.

3. operational_exposure_silver
   - Prepare RTIS mileage and emergency-event intervals for joining to wheel inspections.

### 2.2 Gold datasets to build first

1. wheel_measurement_gold
   - Equipment-level snapshot of the latest valid measurement state.

2. wheel_asset_timeline
   - Chronological view of measurements, interventions, and maintenance events per wheel/equipment.

3. wheel_health_snapshot
   - Current health state with current geometry, wear delta, and confidence flags.

## 3. Data quality rules

### 3.1 Required quality controls

- Reject or flag sentinel dates such as 1900-01-01.
- Flag missing or impossible timestamps.
- Standardise units where possible and preserve the source unit.
- Detect duplicate business events.
- Track data quality through explicit columns such as quality_flags and source_lineage.

### 3.2 Quality flag taxonomy

- valid
- invalid_timestamp
- sentinel_date
- impossible_value
- duplicate_record
- missing_required_field

## 4. Identity and join strategy

### 4.1 Wheel identity path

The core identity chain should be validated as:

```text
wheel measurement -> equipment register -> locomotive assignment
```

### 4.2 Join principles

- Always preserve point-in-time correctness.
- Never use future measurements to compute past features.
- Use effective-dated joins where historical assignment matters.
- Keep unmatched rows visible with explicit quality flags rather than silently dropping them.

## 5. Feature engineering plan

### 5.1 Wheel health features

- current diameter
- flange thickness
- root/tread-related geometry
- wear delta versus previous valid measurement
- wear rate over time
- measurement confidence flag

### 5.2 Maintenance and defect features

- time since last intervention
- recurring maintenance pattern
- defect category presence
- maintenance outcome proxy

### 5.3 Operational exposure features

- distance between inspections
- emergency-event count in the interval
- operating time proxy
- route/location exposure once the identifier reconciliation is complete

## 6. Implementation plan

### Phase 1: foundation

1. Create Silver transformation modules for wheel measurements and maintenance events.
2. Standardise schemas and quality flags.
3. Write regression tests for each transformation.

### Phase 2: integration

1. Join Silver wheel measurements to equipment and locomotive context.
2. Build the first Gold timeline and health snapshot datasets.
3. Generate a basic data-quality report.

### Phase 3: enrichment

1. Add interval-based operational exposure features.
2. Add route/load/context enrichment once the source reconciliation is validated.
3. Evaluate explainable rules and baseline abnormal-wear detection.

## 7. Delivery milestones

- Milestone 1: Silver wheel measurement dataset with quality flags.
- Milestone 2: Gold equipment-level wheel health snapshot.
- Milestone 3: Wheel asset timeline with maintenance and measurement events.
- Milestone 4: Interval-based exposure features and abnormal-wear rules.

## 8. Engineering notes

- Keep transformations deterministic and reproducible.
- Store SQL and Python logic separately.
- Write tests before adding more complex transformations.
- Treat every feature as traceable back to Bronze values.
