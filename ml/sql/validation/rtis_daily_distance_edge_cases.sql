-- Quantify raw daily-sum RTIS edge cases for the WAP7 cohort.  Values are not
-- deduplicated or interpolated: this is evidence for the final business rule.
WITH base AS (
    SELECT r.RlkdLocoNumber AS loco_number, CAST(r.RlkdReportDate AS date) AS report_date,
           r.RlkdDivision AS division, CAST(r.RlkdTotalDistance AS decimal(18,3)) AS distance_km,
           r.RlkdSlamEntryDate AS loaded_at
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS l ON l.LomNumber = r.RlkdLocoNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
), marked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY loco_number, report_date, division, distance_km ORDER BY loaded_at, (SELECT 0)) AS exact_duplicate_rank
    FROM base
), daily AS (
    SELECT loco_number, report_date, SUM(distance_km) AS daily_km,
           COUNT_BIG(*) AS raw_report_count,
           COUNT(DISTINCT division) AS division_count,
           SUM(CASE WHEN exact_duplicate_rank > 1 THEN 1 ELSE 0 END) AS duplicate_reload_row_count
    FROM marked GROUP BY loco_number, report_date
), sequenced AS (
    SELECT *, LAG(report_date) OVER (PARTITION BY loco_number ORDER BY report_date) AS prior_report_date
    FROM daily
)
SELECT metric, value FROM (
    SELECT 'daily_loco_records' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM sequenced
    UNION ALL SELECT 'negative_daily_km', CAST(COUNT(CASE WHEN daily_km < 0 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'zero_daily_km', CAST(COUNT(CASE WHEN daily_km = 0 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'daily_km_below_10', CAST(COUNT(CASE WHEN daily_km > 0 AND daily_km < 10 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'daily_km_200_to_900', CAST(COUNT(CASE WHEN daily_km >= 200 AND daily_km <= 900 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'daily_km_over_1500', CAST(COUNT(CASE WHEN daily_km > 1500 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'daily_km_over_2500', CAST(COUNT(CASE WHEN daily_km > 2500 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'max_daily_km', CAST(MAX(daily_km) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'multi_division_days', CAST(COUNT(CASE WHEN division_count > 1 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'days_with_exact_duplicate_reload_rows', CAST(COUNT(CASE WHEN duplicate_reload_row_count > 0 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'exact_duplicate_reload_rows', CAST(SUM(duplicate_reload_row_count) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'reporting_gaps_over_1_day', CAST(COUNT(CASE WHEN DATEDIFF(day, prior_report_date, report_date) > 1 THEN 1 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'missing_calendar_days_in_gaps', CAST(SUM(CASE WHEN DATEDIFF(day, prior_report_date, report_date) > 1 THEN DATEDIFF(day, prior_report_date, report_date) - 1 ELSE 0 END) AS decimal(19,2)) FROM sequenced
    UNION ALL SELECT 'max_reporting_gap_days', CAST(MAX(DATEDIFF(day, prior_report_date, report_date)) AS decimal(19,2)) FROM sequenced
) AS metrics ORDER BY metric;
