-- Read-only coverage and quality check for wayside (WILD/OMRS) wheel-load and
-- condition signals. String fields are preserved in raw extraction later; this
-- query only measures whether they are populated/parseable for WAP7.
WITH cohort AS (
    SELECT lm.LomId, lm.LomNumber
    FROM LocoMaster AS lm
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = 'WAP7'
),
matched AS (
    SELECT o.*, c.LomId
    FROM OMRSLocoDefectDetails AS o
    INNER JOIN cohort AS c ON c.LomNumber = o.locoNo
)
SELECT
    COUNT_BIG(*) AS Wap7Rows,
    COUNT(DISTINCT LomId) AS Wap7Locomotives,
    COUNT_BIG(CASE WHEN NULLIF(LTRIM(RTRIM(wildWheelWeightTonnes)), '') IS NOT NULL THEN 1 END) AS WheelWeightPopulated,
    COUNT_BIG(CASE WHEN TRY_CONVERT(decimal(12,3), wildWheelWeightTonnes) IS NOT NULL THEN 1 END) AS WheelWeightNumeric,
    MIN(TRY_CONVERT(decimal(12,3), wildWheelWeightTonnes)) AS MinWheelWeightTonnes,
    MAX(TRY_CONVERT(decimal(12,3), wildWheelWeightTonnes)) AS MaxWheelWeightTonnes,
    COUNT_BIG(CASE WHEN NULLIF(LTRIM(RTRIM(wildPeakWheelImpactTonnes)), '') IS NOT NULL THEN 1 END) AS ImpactPopulated,
    COUNT_BIG(CASE WHEN NULLIF(LTRIM(RTRIM(railBamBearingFaultCode)), '') IS NOT NULL THEN 1 END) AS BearingCodePopulated,
    MIN(TRY_CONVERT(datetime2, eventLocalDateTime)) AS MinParsedEventTime,
    MAX(TRY_CONVERT(datetime2, eventLocalDateTime)) AS MaxParsedEventTime
FROM matched;
