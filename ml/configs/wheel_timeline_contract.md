# Wheel Timeline Contract v1.0.0

The V1 timeline is at **equipment/wheelset candidate** level, keyed by
`wheelset_equipment_id`. It must not be described as an individual wheel-level
timeline until the `wsmEquipmentId` business semantics are approved.

| Tier | Criteria | Use |
| --- | --- | --- |
| Gold A | One assignment interval, validated measurements, complete interval exposure and validated business rules | ML training/benchmarking |
| Gold B | Exactly one valid assignment interval and accepted Silver measurement | Timeline analytics and exposure construction |
| Gold C | No interval or multiple intervals | Audit and data improvement only |

Required fields include measurement/equipment IDs and time, assignment-history
ID and interval, locomotive ID/type, geometry, Silver quality flags, tier,
exclusion reason, contract version and lineage.

A measurement is eligible only if `start <= measurement_time <= end`, treating
a null end date as open-ended. No arbitrary choice is made between overlaps.
