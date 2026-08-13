-- Compare candidate aggregation rules. The purpose is to test physical
-- plausibility and duplicate/update behaviour, not to silently approve a rule.
WITH base AS (
    SELECT r.RlkdId, r.RlkdLocoNumber AS loco_number, CAST(r.RlkdReportDate AS date) AS report_date,
        r.RlkdDivision AS division, CAST(r.RlkdTotalDistance AS decimal(18,3)) AS distance_km,
        r.RlkdSlamEntryDate AS loaded_at
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS lm ON lm.LomNumber = r.RlkdLocoNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
      AND r.RlkdReportDate >= '{{START_DATE}}' AND r.RlkdReportDate < '{{END_DATE}}'
), ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY loco_number, report_date, division, distance_km ORDER BY loaded_at DESC, RlkdId DESC) AS exact_rank,
        ROW_NUMBER() OVER (PARTITION BY loco_number, report_date, division ORDER BY loaded_at DESC, RlkdId DESC) AS division_rank
    FROM base
), daily AS (
    SELECT loco_number, report_date,
        SUM(distance_km) AS raw_sum_km,
        SUM(CASE WHEN exact_rank = 1 THEN distance_km END) AS exact_dedup_sum_km,
        SUM(CASE WHEN division_rank = 1 THEN distance_km END) AS latest_division_sum_km,
        COUNT_BIG(*) AS raw_rows,
        SUM(CASE WHEN exact_rank = 1 THEN 1 ELSE 0 END) AS exact_dedup_rows,
        SUM(CASE WHEN division_rank = 1 THEN 1 ELSE 0 END) AS latest_division_rows
    FROM ranked
    GROUP BY loco_number, report_date
)
SELECT 'loco_day_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM daily
UNION ALL SELECT 'max_raw_sum_km', CAST(MAX(raw_sum_km) AS decimal(19,2)) FROM daily
UNION ALL SELECT 'max_exact_dedup_sum_km', CAST(MAX(exact_dedup_sum_km) AS decimal(19,2)) FROM daily
UNION ALL SELECT 'max_latest_division_sum_km', CAST(MAX(latest_division_sum_km) AS decimal(19,2)) FROM daily
UNION ALL SELECT 'latest_division_days_over_1500km', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE latest_division_sum_km > 1500
UNION ALL SELECT 'latest_division_days_over_2500km', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE latest_division_sum_km > 2500
UNION ALL SELECT 'days_changed_by_exact_dedup', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE raw_sum_km <> exact_dedup_sum_km
UNION ALL SELECT 'days_changed_by_latest_division', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM daily WHERE exact_dedup_sum_km <> latest_division_sum_km;
