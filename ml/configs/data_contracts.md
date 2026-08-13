# Data Contracts

## `silver.wheel_measurements` v1.0.0

- **Grain:** one source `WheelSetMeasurements.wsmId` record; do not yet claim a
  one-record-per-wheel grain.
- **Business time:** `wsmUpdatedOn`, standardised as `measurement_timestamp`.
- **Identity candidates:** `wsmId` (`measurement_record_id`) and
  `wsmEquipmentId` (`wheelset_equipment_id`). Equipment-to-wheel and
  effective-dated locomotive assignment remain validation gates.
- **Immutability:** Bronze is never modified. Silver preserves source values,
  standardised values, flags and contract version.
- **Quarantine:** missing/sentinel timestamp or duplicate measurement record ID.
- **Acceptance with flags:** missing equipment identity or implausible measured
  values. These records remain auditable but must be filtered from a feature by
  its explicit eligibility rule.
- **Point-in-time rule:** no feature may use a record with
  `measurement_timestamp` after its score timestamp.

## `silver.rtis_mileage` v1.0.0

- **Grain:** one `RtisLocoKmDetails.RlkdId` source event.
- **Business time:** `RlkdReportDate`, standardised as `event_timestamp`.
- **Identity:** `RlkdId` (`rtis_mileage_event_id`) and locomotive number.
- **Measurement:** `RlkdTotalDistance`, standardised as
  `reported_distance_km`; its cumulative-versus-interval semantics must be
  confirmed before it is summed or differenced.
- **Quarantine:** missing/sentinel event time or duplicate event ID.
- **Accepted-with-flag:** repeated loco/report-date/division/distance business
  reports. These are retained in Silver but must not be summed; see
  `docs/rtis_semantics.md`.
- **Point-in-time rule:** exposure for an inspection interval uses only events
  at or before the interval end and after its start, with an explicit boundary
  convention in the Engineering Layer.

## `silver.loco_equipment_history` v1.0.0

- **Grain:** one `LocoEquipmentsHistory.LoehId` assignment-history record.
- **Business interval:** `LoehProvisionDate` through `LoehRemovedDate`,
  standardised as `assignment_start_timestamp` and
  `assignment_end_timestamp`.
- **Identity:** equipment ID and locomotive ID are both mandatory.
- **Quarantine:** missing IDs, invalid provision date, removed-before-provision
  interval, or duplicate history ID.
- **Timeline eligibility:** a measurement is eligible only when it falls in
  exactly one accepted assignment interval. Interval overlap is evaluated in a
  separate validation report; this contract does not choose a winner.
