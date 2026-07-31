-- Cross-check low-RTIS-km idle blocks against FOIS shed in/out records.
-- This is validation evidence, not a rule that every low-km day is in shed.
WITH daily AS (
    SELECT CAST(RlkdReportDate AS date) AS report_date,
           SUM(CAST(RlkdTotalDistance AS decimal(18,3))) AS daily_km
    FROM RtisLocoKmDetails
    WHERE RlkdLocoNumber = '30201'
    GROUP BY CAST(RlkdReportDate AS date)
), low_days AS (
    SELECT report_date, daily_km,
           LAG(report_date) OVER (ORDER BY report_date) AS prior_report_date
    FROM daily WHERE daily_km < 10
), marked AS (
    SELECT *, SUM(CASE WHEN prior_report_date = DATEADD(day, -1, report_date) THEN 0 ELSE 1 END)
        OVER (ORDER BY report_date ROWS UNBOUNDED PRECEDING) AS idle_group
    FROM low_days
), idle_blocks AS (
    SELECT idle_group, MIN(report_date) AS idle_from, MAX(report_date) AS idle_to,
           COUNT(*) AS idle_days, AVG(daily_km) AS avg_idle_km
    FROM marked GROUP BY idle_group HAVING COUNT(*) >= 3
), shed_events AS (
    SELECT 'foisshedin' AS shed_source, LocoNumber,
           EntryDateTime AS shed_start,
           COALESCE(OutDateTime, EntryDateTime) AS shed_end
    FROM foisshedin WHERE LocoNumber = '30201'
    UNION ALL
    SELECT 'foisshedout', LocoNumber,
           ShedStartTime,
           COALESCE(ShedEndtime, OutDateTime, ShedStartTime)
    FROM foisshedout WHERE LocoNumber = '30201'
)
SELECT b.idle_from, b.idle_to, b.idle_days, CAST(b.avg_idle_km AS decimal(18,2)) AS avg_idle_km,
       COUNT(e.shed_source) AS overlapping_shed_records,
       MIN(e.shed_start) AS first_overlapping_shed_start,
       MAX(e.shed_end) AS last_overlapping_shed_end,
       CASE WHEN COUNT(e.shed_source) > 0 THEN 'SHED_EVIDENCE_PRESENT'
            ELSE 'NO_SHED_EVIDENCE_IN_CURRENT_FOIS_TABLES' END AS shed_crosscheck_status
FROM idle_blocks AS b
LEFT JOIN shed_events AS e
  ON CAST(e.shed_start AS date) <= b.idle_to
 AND CAST(e.shed_end AS date) >= b.idle_from
GROUP BY b.idle_from, b.idle_to, b.idle_days, b.avg_idle_km
ORDER BY b.idle_from;
