# Operational Exposure v1.0 contract

**Grain:** one released Gold-B consecutive inspection interval.  **Boundary:**
`interval_start_timestamp < source_event_timestamp <= interval_end_timestamp`.

| Feature group | Columns | Status and interpretation |
| --- | --- | --- |
| Interval identity | `operational_exposure_id`, measurement IDs, equipment ID, locomotive ID/number, timestamps, `interval_days` | Released factual boundary. |
| RTIS emergency-source events | `emergency_event_count`, `emergency_event_type_count`, `emergency_event_types` | Timestamped source-event occurrence. Event-code engineering meaning is still pending; do not equate a code with a physical braking mechanism without owner confirmation. |
| Job-card context | `maintenance_jobcard_count` | Job-card **creation** events only; not work completion, effectiveness, or a wheel-specific intervention. |
| RTIS reporting context | report/division/duplicate counts, earliest/latest reporting timestamps, reporting days, coverage percent | Provisional reporting metadata. It describes source coverage, not physical movement, route, or distance. |
| Physical distance | `distance_km`, `distance_status` | `distance_km` must be null and status must remain `BLOCKED_PENDING_SOURCE_CONFIRMATION`. No downstream feature may override it. |

## Quality and release controls

- `quality_flags=no_rtis_reports_in_interval` means no RTIS reporting metadata
  occurs inside the interval; it does not mean no locomotive movement.
- Every materialisation records immutable input checksums in its quality report.
- A feature consumer must use the feature status column, not infer readiness
  merely because a numerical column is populated.
- Exposure coverage is never imputed as zero distance or zero route activity.
