-- Test whether RTISLOCOKM is a distinct, usable movement feed or a staging copy.
WITH base AS (
    SELECT r.loco_NUMBER, CAST(r.report_DATE AS date) AS report_date, r.division,
        TRY_CONVERT(decimal(18,3), r.total_DISTANCE) AS distance_value
    FROM RTISLOCOKM AS r
    INNER JOIN LocoMaster AS l ON TRY_CONVERT(varchar(20), r.loco_NUMBER) = l.LomNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
), daily AS (
    SELECT loco_NUMBER, report_date, COUNT_BIG(*) AS report_count,
        SUM(distance_value) AS daily_sum, MAX(distance_value) AS daily_max
    FROM base GROUP BY loco_NUMBER, report_date
)
SELECT metric, value FROM (
    SELECT 'cohort_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM base
    UNION ALL SELECT 'distinct_locomotives', CAST(COUNT(DISTINCT loco_NUMBER) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'invalid_distance_values', CAST(COUNT(CASE WHEN distance_value IS NULL THEN 1 END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'negative_distance_values', CAST(COUNT(CASE WHEN distance_value < 0 THEN 1 END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'max_row_distance', CAST(MAX(distance_value) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'max_daily_sum', CAST(MAX(daily_sum) AS decimal(19,2)) FROM daily
    UNION ALL SELECT 'max_daily_max', CAST(MAX(daily_max) AS decimal(19,2)) FROM daily
    UNION ALL SELECT 'multi_report_loco_days', CAST(COUNT(CASE WHEN report_count > 1 THEN 1 END) AS decimal(19,2)) FROM daily
) AS metrics
ORDER BY metric;
