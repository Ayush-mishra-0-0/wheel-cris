-- Evaluate whether MovementRegister can become a completed-movement distance ledger.
-- It reports evidence only; no distance is released by this query.
WITH base AS (
    SELECT m.MorId, m.MorLocoId, m.MorEntryDatetime, m.MorLeaveDateTime,
        m.MorReadyDateTime, m.MorScheduleId, m.MorTrainNo, m.MorOutStation,
        m.MorBaseShed, m.MorLomStatus, m.MorSpeedometerReadingIn AS meter_in,
        m.MorSpeedometerReadingOut AS meter_out, m.MorMilageEarned AS mileage_earned,
        m.MorMilageEarnedCumulative AS mileage_cumulative,
        DATEDIFF(minute, m.MorEntryDatetime, m.MorLeaveDateTime) AS movement_minutes,
        m.MorSpeedometerReadingOut - m.MorSpeedometerReadingIn AS meter_delta
    FROM MovementRegister AS m
    INNER JOIN LocoMaster AS l ON l.LomId = m.MorLocoId
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
), classified AS (
    SELECT *, CASE WHEN MorLeaveDateTime IS NOT NULL AND meter_in IS NOT NULL AND meter_out IS NOT NULL
                      AND meter_delta BETWEEN 0 AND 2000 AND movement_minutes BETWEEN 1 AND 10080
                    THEN 1 ELSE 0 END AS candidate_completed_movement
    FROM base
)
SELECT CAST('summary' AS varchar(30)) AS result_type, metric, value, NULL AS status_value
FROM (
    SELECT 'cohort_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM classified
    UNION ALL SELECT 'rows_with_leave_time', CAST(COUNT(MorLeaveDateTime) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'rows_with_train_number', CAST(COUNT(CASE WHEN MorTrainNo IS NOT NULL AND MorTrainNo <> 0 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'rows_with_out_station', CAST(COUNT(CASE WHEN MorOutStation IS NOT NULL AND MorOutStation <> 0 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'rows_with_schedule', CAST(COUNT(CASE WHEN MorScheduleId IS NOT NULL AND MorScheduleId <> 0 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'candidate_completed_movements', CAST(COUNT(CASE WHEN candidate_completed_movement = 1 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'candidate_rows_mileage_matches_meter_delta', CAST(COUNT(CASE WHEN candidate_completed_movement = 1 AND mileage_earned = meter_delta THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'candidate_rows_with_nonzero_meter_delta', CAST(COUNT(CASE WHEN candidate_completed_movement = 1 AND meter_delta > 0 THEN 1 END) AS decimal(19,2)) FROM classified
    UNION ALL SELECT 'candidate_max_meter_delta', CAST(MAX(CASE WHEN candidate_completed_movement = 1 THEN meter_delta END) AS decimal(19,2)) FROM classified
) AS summary
UNION ALL
SELECT 'status_distribution', 'MorLomStatus', CAST(COUNT_BIG(*) AS decimal(19,2)), CAST(MorLomStatus AS varchar(100))
FROM classified GROUP BY MorLomStatus
ORDER BY result_type, metric, status_value;
