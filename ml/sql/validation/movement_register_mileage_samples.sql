-- Inspect actual candidate-movement records for the configured cohort.
SELECT TOP (100)
    l.LomNumber, m.MorId, m.MorEntryDatetime, m.MorLeaveDateTime,
    m.MorSpeedometerReadingIn, m.MorSpeedometerReadingOut,
    m.MorSpeedometerReadingOut - m.MorSpeedometerReadingIn AS speedometer_delta,
    m.MorMilageEarned, m.MorMilageEarnedCumulative, m.morKM,
    m.MorScheduleId, m.MorTrainNo, m.MorBaseShed
FROM MovementRegister AS m
INNER JOIN LocoMaster AS l ON l.LomId = m.MorLocoId
INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
WHERE lt.LotTypeName = '{{COHORT}}'
ORDER BY m.MorEntryDatetime DESC, m.MorId DESC;
