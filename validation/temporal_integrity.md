# Temporal Integrity

**Status:** In progress.

Timeline rules to validate before feature engineering:

- A measurement must map to one—and only one—valid assignment interval.
- Assignment intervals may not overlap for the same equipment without an
  explicit business explanation.
- Measurement time must fall within the assignment interval.
- The first production eligibility policy is exactly one valid
  `LocoEquipmentsHistory` interval per measurement. Zero or multiple matches
  are exclusion states, not a tie-breaker opportunity.
- The validated Gold-B timeline is an equipment/wheelset-candidate timeline
  until `wsmEquipmentId` semantics are approved; it is not yet evidence of a
  unique individual-wheel identity.
- Diameter increases must be explained by turning/reprofiling/replacement or
  retained as a data-quality exception.
- No feature can use events occurring after its score timestamp.
