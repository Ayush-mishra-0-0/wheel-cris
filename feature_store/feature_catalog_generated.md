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
