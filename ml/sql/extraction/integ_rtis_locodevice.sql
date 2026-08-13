-- Bronze/raw RTIS loco-device extract: RTIS device to loco/shed assignment.
-- Cohort-filtered via LocoMaster.
SELECT
    d.irld,
    d.DeviceID,
    d.LocoNumber,
    lm.LomId AS LocoId,
    d.LocoType,
    d.LocoShed,
    d.Phase,
    d.RecordCreatedTimestamp
FROM Integ_rtis_Locodevice AS d
INNER JOIN LocoMaster AS lm
    ON lm.LomNumber = d.LocoNumber
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
