-- Read-only sample of the matched WAP7 wayside records, retained solely to
-- inspect the serialisation of load/time fields before defining parsers.
WITH cohort AS (
    SELECT lm.LomId, lm.LomNumber
    FROM LocoMaster AS lm
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = 'WAP7'
)
SELECT
    c.LomId,
    o.locoNo,
    o.eventLocalDateTime,
    o.wildWheelWeightTonnes,
    o.wildPeakWheelImpactTonnes,
    o.wildWheelImpactDynamicKiloNewtons,
    o.axleSpeed,
    o.railBamBearingFaultCode,
    o.railBamBearingAlertLevelKey
FROM OMRSLocoDefectDetails AS o
INNER JOIN cohort AS c ON c.LomNumber = o.locoNo
ORDER BY o.omrsDataEntryDateTime DESC;
