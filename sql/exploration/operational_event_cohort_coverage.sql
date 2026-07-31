-- Read-only coverage check: verifies that the detailed operational tables can
-- be matched to the configured WAP7 cohort by displayed locomotive number.
WITH cohort AS (
    SELECT lm.LomId, lm.LomNumber
    FROM LocoMaster AS lm
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = 'WAP7'
)
SELECT
    'RtisLocoKmDetails' AS SourceTable,
    COUNT_BIG(*) AS TotalRows,
    COUNT_BIG(CASE WHEN c.LomId IS NOT NULL THEN 1 END) AS CohortMatchedRows,
    COUNT(DISTINCT CASE WHEN c.LomId IS NOT NULL THEN c.LomId END) AS CohortLocomotives,
    MIN(CASE WHEN c.LomId IS NOT NULL THEN r.RlkdReportDate END) AS CohortMinEventTime,
    MAX(CASE WHEN c.LomId IS NOT NULL THEN r.RlkdReportDate END) AS CohortMaxEventTime
FROM RtisLocoKmDetails AS r
LEFT JOIN cohort AS c ON c.LomNumber = r.RlkdLocoNumber

UNION ALL

SELECT
    'INTEG_rtisLocoEmergencyData',
    COUNT_BIG(*),
    COUNT_BIG(CASE WHEN c.LomId IS NOT NULL THEN 1 END),
    COUNT(DISTINCT CASE WHEN c.LomId IS NOT NULL THEN c.LomId END),
    MIN(CASE WHEN c.LomId IS NOT NULL THEN e.EVENT_TRANSMISSION_TIME END),
    MAX(CASE WHEN c.LomId IS NOT NULL THEN e.EVENT_TRANSMISSION_TIME END)
FROM INTEG_rtisLocoEmergencyData AS e
LEFT JOIN cohort AS c ON c.LomNumber = e.LOCO_NO

UNION ALL

SELECT
    'FOIS_LocoLocation_History',
    COUNT_BIG(*),
    COUNT_BIG(CASE WHEN c.LomId IS NOT NULL THEN 1 END),
    COUNT(DISTINCT CASE WHEN c.LomId IS NOT NULL THEN c.LomId END),
    MIN(CASE WHEN c.LomId IS NOT NULL THEN f.FOISrptgtime END),
    MAX(CASE WHEN c.LomId IS NOT NULL THEN f.FOISrptgtime END)
FROM FOIS_LocoLocation_History AS f
LEFT JOIN cohort AS c ON c.LomNumber = f.LocoNumb;
