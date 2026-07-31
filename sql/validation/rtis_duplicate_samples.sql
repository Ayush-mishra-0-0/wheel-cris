WITH base AS (
    SELECT r.RlkdId, r.RlkdLocoNumber AS loco_number, CAST(r.RlkdReportDate AS date) AS report_date,
        r.RlkdDivision AS division, r.RlkdTotalDistance AS distance_km, r.RlkdSlamEntryDate AS loaded_at
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS lm ON lm.LomNumber = r.RlkdLocoNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
      AND r.RlkdReportDate >= '{{START_DATE}}' AND r.RlkdReportDate < '{{END_DATE}}'
), repeated AS (
    SELECT loco_number, report_date, division, distance_km
    FROM base GROUP BY loco_number, report_date, division, distance_km HAVING COUNT_BIG(*) > 1
)
SELECT TOP (50) b.*
FROM base AS b
INNER JOIN repeated AS r ON r.loco_number = b.loco_number AND r.report_date = b.report_date AND r.division = b.division AND r.distance_km = b.distance_km
ORDER BY b.loco_number, b.report_date, b.division, b.loaded_at, b.RlkdId;
