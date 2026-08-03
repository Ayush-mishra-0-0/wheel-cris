-- Bronze/raw daily overdue-locomotive extract: home shed and schedule-overdue
-- context, keyed by locomotive number. Cohort-filtered via LocoMaster.
SELECT
    d.ID,
    d.LocoNumber,
    d.LocoType,
    d.HomeShed,
    d.EntryDate,
    d.LastScheduleDoneAt,
    d.SpeedometerReadingLastSchVisit,
    d.RunningKmFromLastSchVisit,
    d.ExcessKmsOverLimit,
    d.LastVisit,
    d.LastScheduleVisit,
    d.RTISCurrentLocation
FROM DailyOverdueLocoCount AS d
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = d.LocoNumber
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
