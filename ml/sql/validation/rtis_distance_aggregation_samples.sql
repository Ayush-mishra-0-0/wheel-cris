WITH base AS (
    SELECT r.RlkdId, r.RlkdLocoNumber AS loco_number, CAST(r.RlkdReportDate AS date) AS report_date,
        r.RlkdDivision AS division, CAST(r.RlkdTotalDistance AS decimal(18,3)) AS distance_km, r.RlkdSlamEntryDate AS loaded_at
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS lm ON lm.LomNumber = r.RlkdLocoNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = '{{COHORT}}' AND r.RlkdReportDate >= '{{START_DATE}}' AND r.RlkdReportDate < '{{END_DATE}}'
), ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY loco_number, report_date, division ORDER BY loaded_at DESC, RlkdId DESC) AS division_rank FROM base
), daily AS (
    SELECT loco_number, report_date, SUM(CASE WHEN division_rank = 1 THEN distance_km END) AS latest_division_sum_km
    FROM ranked GROUP BY loco_number, report_date
), high_days AS (
    SELECT TOP (20) * FROM daily ORDER BY latest_division_sum_km DESC
)
SELECT r.loco_number, r.report_date, r.division, r.distance_km, r.loaded_at, r.RlkdId
FROM ranked AS r INNER JOIN high_days AS h ON h.loco_number = r.loco_number AND h.report_date = r.report_date
ORDER BY h.latest_division_sum_km DESC, r.loco_number, r.report_date, r.division, r.loaded_at;
