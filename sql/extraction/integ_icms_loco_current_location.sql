-- Bronze/raw current-location extract: snapshot zone/division/station per loco.
-- Cohort-filtered via LocoMaster.
SELECT
    loc.LLid,
    loc.locoNumber,
    lm.LomId AS LocoId,
    loc.currentZone,
    loc.currentDivision,
    loc.currentStation,
    loc.trainNumber,
    loc.trainStartDate,
    loc.lastEventTime,
    loc.lastEvent,
    loc.RecordCreatedTimestamp
FROM Integ_icms_LocoCurrentLocation AS loc
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = loc.locoNumber
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
