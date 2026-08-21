# Generated Feature Store v1.0 catalog

Generated from `configs/engineering_feature_specification_v1.json`; do not edit manually.

| Feature | Status | Evidence | Owner | Formula |
| --- | --- | --- | --- | --- |
| Inspection interval duration | READY | Measured | Behaviour | (interval_end_timestamp - interval_start_timestamp) / 86,400 seconds |
| Point-in-time assignment quality | READY | Observed | Identity | timeline_quality_tier emitted by Business Truth v1.0 |
| Raw endpoint diameter change | READY_WITH_CAVEAT | Derived | Behaviour | interval_end_wsmDiaN - interval_start_wsmDiaN |
| RTIS source-event count | READY_WITH_CAVEAT | Observed | Exposure | COUNT(DISTINCT IrledId WHERE start < EVENT_TRANSMISSION_TIME <= end AND normalised LOCO_NO matches) |
| Maintenance job-card creation count | READY_WITH_CAVEAT | Observed | Maintenance | COUNT(DISTINCT SejId WHERE start < SejCreatedOn <= end AND SejLocoId matches) |
| RTIS reporting coverage | READY_WITH_CAVEAT | Derived | Exposure | 100 * distinct RTIS report dates in interval / interval_days |
| Static locomotive axle-load configuration | READY_FOR_MATERIALISATION | Measured | Exposure | LocoTypes.LotAxelLoad joined via LocoMaster.LomType |
| Wheel position (1-12) | READY_FOR_MATERIALISATION | Measured | Identity | WheelFormationTemplates.WftWheelPos joined on (wsmWheelSetPosition, wsmW1EndType) |
| Axle / wheelset position | READY_FOR_MATERIALISATION | Measured | Identity | wsmWheelSetPosition at interval end |
| Wheel inspection count | READY_FOR_MATERIALISATION | Derived | Behaviour | COUNT(WheelSetMeasurements rows with same wsmWRId AND wsmUpdatedOn <= interval_end_timestamp) |
| Wheel profile (2-class) | READY_WITH_CAVEAT | Measured | Maintenance | LocoWheelRegister.LwrWheelProfile |
| Wheel maintenance schedule | READY_WITH_CAVEAT | Measured | Maintenance | LocoWheelRegister.LwrScheduleId |
| Home shed | READY_WITH_CAVEAT | Measured | Exposure | DailyOverdueLocoCount.HomeShed latest per locomotive with EntryDate <= interval_end_timestamp |
| Defect zone | READY_WITH_CAVEAT | Measured | Exposure | OnlineDefects_LogHistory.OldZone latest per OldLocoId with OldDateOccurance <= interval_end_timestamp |
| Defect division | READY_WITH_CAVEAT | Measured | Exposure | OnlineDefects_LogHistory.OldDivision latest per OldLocoId with OldDateOccurance <= interval_end_timestamp |
| Wheel age proxy (days, EmrDoR-anchored) | READY_WITH_CAVEAT | Derived | Identity | interval_end_timestamp - cascade[EmrDoR per wsmEquipmentId -> EmrDoM -> wsmProvDate at interval end]; date source recorded in wheel_age_date_source |
| Raw turning indicator | READY_WITH_CAVEAT | Observed | Maintenance | wsmturning1 at the interval-end measurement |
| Days since last wheel turning | READY_WITH_CAVEAT | Derived | Maintenance | interval_end_timestamp - MAX(wsmUpdatedOn WHERE wsmEquipmentId = interval-end equipment AND wsmturning1 = 1 AND wsmUpdatedOn <= interval_end_timestamp) |
| Physical distance travelled | READY_FOR_MATERIALISATION | Observed | Exposure | owner-approved (2026-08-05) daily aggregation: deduped per-loco per-day SUM of division km with combined outlier rejection (07_safe_rtis_daily_aggregation.py), summed over interval (start, end] |
