-- Profile current FOIS/RTIS location feed, including WAP7 coverage and encoded coordinates.
WITH base AS (
    SELECT f.IntgFLid, f.LocoNumb, f.RTISEvnttime, f.FOISrptgtime,
        f.RTISLatd, f.RTISLngt, f.RecordCreatedTimestamp,
        CASE WHEN lt.LotTypeName = '{{COHORT}}' THEN 1 ELSE 0 END AS is_cohort
    FROM INTEG_FOIS_LocoLocation AS f
    LEFT JOIN LocoMaster AS l ON f.LocoNumb = l.LomNumber
    LEFT JOIN LocoTypes AS lt ON lt.LotId = l.LomType
)
SELECT metric, value FROM (
    SELECT 'all_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM base
    UNION ALL SELECT 'all_distinct_locos', CAST(COUNT(DISTINCT LocoNumb) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'wap7_rows', CAST(COUNT(CASE WHEN is_cohort = 1 THEN 1 END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'wap7_distinct_locos', CAST(COUNT(DISTINCT CASE WHEN is_cohort = 1 THEN LocoNumb END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'rows_with_event_time', CAST(COUNT(RTISEvnttime) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'rows_with_coordinate_pair', CAST(COUNT(CASE WHEN RTISLatd IS NOT NULL AND RTISLngt IS NOT NULL THEN 1 END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'wap7_rows_with_coordinate_pair', CAST(COUNT(CASE WHEN is_cohort = 1 AND RTISLatd IS NOT NULL AND RTISLngt IS NOT NULL THEN 1 END) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'min_raw_latitude', CAST(MIN(RTISLatd) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'max_raw_latitude', CAST(MAX(RTISLatd) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'min_raw_longitude', CAST(MIN(RTISLngt) AS decimal(19,2)) FROM base
    UNION ALL SELECT 'max_raw_longitude', CAST(MAX(RTISLngt) AS decimal(19,2)) FROM base
) AS metrics ORDER BY metric;
