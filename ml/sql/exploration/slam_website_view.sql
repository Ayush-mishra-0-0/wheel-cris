-- Rebuild the SLAM wheel-measurement website table from the live source tables.
-- Verified 2026-08-20: reproduces the site's rows (Before/After Turning, Reason Of
-- Turning, Wheel Profile, Schedule, Measured By, Section, etc.) exactly.
-- (This is the row set the SLAM web UI renders as "wheel readings/measurement".)
SELECT
    lm.LomNumber                                          AS Loco,
    fl.FLocCode + ' (' + fl.FLocName + ')'                AS HomeShed,
    fl.FLocCode + ' (' + fl.FLocName + ')'                AS MeasurementDoneAt,
    lwr.LwrDia1                                           AS MinDiaBogie1,
    lwr.LwrDia2                                           AS MinDiaBogie2,
    CONVERT(date, lwr.LwrUpdatedOn)                       AS [Date],
    CASE lwr.LwrTurningType
        WHEN 0 THEN 'Before Turning'
        WHEN 1 THEN 'After Turning'
        WHEN 2 THEN 'Regular CheckUp'
        ELSE CONVERT(varchar(20), lwr.LwrTurningType)
    END                                                   AS ReadingPurpose,
    wp.WpWheelProfileName                                 AS WheelProfile,
    emp.EmpFullName                                       AS MeasuredBy,
    sec.SecCode                                           AS [Section],
    ISNULL(wrp.WrpName, '--')                             AS ReasonOfTurning,
    st.SctCode                                            AS Schedule,
    lwr.LwrRemarks                                        AS Remarks
FROM LocoWheelRegister AS lwr
INNER JOIN LocoMaster AS lm            ON lm.LomId = lwr.LwrLocoId
LEFT  JOIN FunctionalLocations AS fl   ON fl.FLocId = lwr.LwrFuncLocId
LEFT  JOIN WheelProfile AS wp          ON wp.WpID = lwr.LwrWheelProfile
LEFT  JOIN Employees AS emp            ON emp.EmpId = lwr.LwrTakenBy
LEFT  JOIN Sections AS sec             ON sec.SecId = emp.EmpSection
LEFT  JOIN ScheduleTypes AS st         ON st.SctId = lwr.LwrScheduleId
OUTER APPLY (
    SELECT STRING_AGG(wrp2.WrpName, ', ') AS WrpName
    FROM STRING_SPLIT(lwr.LwrPurpose, ',') AS s
    LEFT JOIN WheelReadingPurpose AS wrp2
        ON wrp2.WrpId = TRY_CAST(LTRIM(RTRIM(s.value)) AS int)
    WHERE TRY_CAST(LTRIM(RTRIM(s.value)) AS int) IS NOT NULL
) AS wrp
WHERE lwr.LwrLocoId = 33762 OR lwr.LwrLocoId = 39023  -- sample locos from the site
ORDER BY lm.LomNumber, lwr.LwrUpdatedOn;