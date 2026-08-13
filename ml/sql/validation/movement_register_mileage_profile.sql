-- Profile a candidate operational mileage ledger for the configured cohort.
-- The query establishes behaviour; it does not approve a distance rule.
WITH base AS (
    SELECT m.MorId, m.MorLocoId, m.MorEntryDatetime, m.MorLeaveDateTime,
        m.MorSpeedometerReadingIn AS speedometer_in,
        m.MorSpeedometerReadingOut AS speedometer_out,
        m.MorMilageEarned AS mileage_earned,
        m.MorMilageEarnedCumulative AS mileage_earned_cumulative,
        m.morKM AS reported_km
    FROM MovementRegister AS m
    INNER JOIN LocoMaster AS l ON l.LomId = m.MorLocoId
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
), derived AS (
    SELECT *,
        speedometer_out - speedometer_in AS speedometer_delta,
        LAG(speedometer_out) OVER (PARTITION BY MorLocoId ORDER BY COALESCE(MorLeaveDateTime, MorEntryDatetime), MorId) AS prior_speedometer_out,
        LAG(mileage_earned_cumulative) OVER (PARTITION BY MorLocoId ORDER BY COALESCE(MorLeaveDateTime, MorEntryDatetime), MorId) AS prior_cumulative
    FROM base
)
SELECT metric, value
FROM (
    SELECT 'cohort_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM derived
    UNION ALL SELECT 'distinct_locomotives', CAST(COUNT(DISTINCT MorLocoId) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'rows_with_entry_timestamp', CAST(COUNT(MorEntryDatetime) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'rows_with_leave_timestamp', CAST(COUNT(MorLeaveDateTime) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'rows_with_speedometer_in_out', CAST(COUNT(CASE WHEN speedometer_in IS NOT NULL AND speedometer_out IS NOT NULL THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'negative_speedometer_deltas', CAST(COUNT(CASE WHEN speedometer_delta < 0 THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'zero_speedometer_deltas', CAST(COUNT(CASE WHEN speedometer_delta = 0 THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'max_speedometer_delta', CAST(MAX(speedometer_delta) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'rows_with_mileage_earned', CAST(COUNT(mileage_earned) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'negative_mileage_earned', CAST(COUNT(CASE WHEN mileage_earned < 0 THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'max_mileage_earned', CAST(MAX(mileage_earned) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'mileage_earned_equals_speedometer_delta', CAST(COUNT(CASE WHEN mileage_earned = speedometer_delta THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'rows_with_cumulative_mileage', CAST(COUNT(mileage_earned_cumulative) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'negative_cumulative_changes', CAST(COUNT(CASE WHEN mileage_earned_cumulative < prior_cumulative THEN 1 END) AS decimal(19,2)) FROM derived
    UNION ALL SELECT 'speedometer_continuity_breaks', CAST(COUNT(CASE WHEN speedometer_in <> prior_speedometer_out THEN 1 END) AS decimal(19,2)) FROM derived
) AS metrics
ORDER BY metric;
