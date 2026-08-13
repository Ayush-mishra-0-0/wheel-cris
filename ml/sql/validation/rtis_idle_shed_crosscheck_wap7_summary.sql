-- Fleet-level evidence for the low-km/shed hypothesis.  Uses daily RTIS sums
-- and retained FOIS shed records; unmatched does not mean "not in shed".
WITH daily AS (
    SELECT r.RlkdLocoNumber AS loco_number, CAST(r.RlkdReportDate AS date) AS report_date,
           SUM(CAST(r.RlkdTotalDistance AS decimal(18,3))) AS daily_km
    FROM RtisLocoKmDetails AS r
    INNER JOIN LocoMaster AS l ON r.RlkdLocoNumber = l.LomNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
    GROUP BY r.RlkdLocoNumber, CAST(r.RlkdReportDate AS date)
), low_days AS (
    SELECT loco_number, report_date, daily_km,
           LAG(report_date) OVER (PARTITION BY loco_number ORDER BY report_date) AS prior_report_date
    FROM daily WHERE daily_km < 10
), marked AS (
    SELECT *, SUM(CASE WHEN prior_report_date = DATEADD(day, -1, report_date) THEN 0 ELSE 1 END)
        OVER (PARTITION BY loco_number ORDER BY report_date ROWS UNBOUNDED PRECEDING) AS idle_group
    FROM low_days
), idle_blocks AS (
    SELECT loco_number, idle_group, MIN(report_date) AS idle_from, MAX(report_date) AS idle_to,
           COUNT(*) AS idle_days
    FROM marked GROUP BY loco_number, idle_group HAVING COUNT(*) >= 3
), shed_events AS (
    SELECT LocoNumber AS loco_number, EntryDateTime AS shed_start,
           COALESCE(OutDateTime, EntryDateTime) AS shed_end FROM foisshedin
    UNION ALL
    SELECT LocoNumber, ShedStartTime,
           COALESCE(ShedEndtime, OutDateTime, ShedStartTime) FROM foisshedout
), classified AS (
    SELECT b.*, CASE WHEN EXISTS (
        SELECT 1 FROM shed_events AS e
        WHERE e.loco_number = b.loco_number
          AND CAST(e.shed_start AS date) <= b.idle_to
          AND CAST(e.shed_end AS date) >= b.idle_from
    ) THEN 1 ELSE 0 END AS has_shed_evidence
    FROM idle_blocks AS b
)
SELECT metric, value FROM (
    SELECT 'idle_blocks_at_least_3_days' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM classified
    UNION ALL SELECT 'blocks_with_shed_evidence', CAST(COUNT(CASE WHEN has_shed_evidence = 1 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'blocks_without_shed_evidence_or_coverage', CAST(COUNT(CASE WHEN has_shed_evidence = 0 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'distinct_locos_with_idle_blocks', CAST(COUNT(DISTINCT loco_number) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'distinct_locos_with_shed_evidence', CAST(COUNT(DISTINCT CASE WHEN has_shed_evidence = 1 THEN loco_number END) AS decimal(19,2)) FROM classified
) AS metrics ORDER BY metric;
