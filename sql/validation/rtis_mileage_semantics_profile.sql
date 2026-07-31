-- Establish the grain and aggregation behaviour of RTIS distance before it is
-- joined to inspection intervals. No interval distances are calculated here.
WITH daily AS (
    SELECT
        RlkdLocoNumber AS loco_number,
        CAST(RlkdReportDate AS date) AS report_date,
        COUNT_BIG(*) AS source_rows,
        COUNT(DISTINCT RlkdDivision) AS divisions,
        SUM(RlkdTotalDistance) AS summed_distance_km,
        MIN(RlkdTotalDistance) AS min_row_distance_km,
        MAX(RlkdTotalDistance) AS max_row_distance_km
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS lm ON lm.LomNumber = r.RlkdLocoNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
      AND r.RlkdReportDate >= '{{START_DATE}}'
      AND r.RlkdReportDate < '{{END_DATE}}'
    GROUP BY RlkdLocoNumber, CAST(RlkdReportDate AS date)
)
SELECT 'loco_day_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM daily
UNION ALL SELECT 'loco_days_with_multiple_source_rows', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE source_rows > 1
UNION ALL SELECT 'loco_days_with_multiple_divisions', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE divisions > 1
UNION ALL SELECT 'loco_days_with_negative_summed_distance', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE summed_distance_km < 0
UNION ALL SELECT 'loco_days_with_zero_summed_distance', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE summed_distance_km = 0
UNION ALL SELECT 'max_daily_summed_distance_km', CAST(MAX(summed_distance_km) AS decimal(19,2)) FROM daily;
