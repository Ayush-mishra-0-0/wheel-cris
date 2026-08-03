-- Bronze/raw wheel-register extract: turning events, skid flags, wheel profile
-- and schedule context at the wheelset grain. Cohort-filtered via LocoMaster.
SELECT
    lwr.LwrId,
    lwr.LwrLocoId,
    lwr.LwrDia1,
    lwr.LwrDia2,
    lwr.LwrTurningType,
    lwr.LwrWsmSkidTurn,
    lwr.LwrWheelProfile,
    lwr.LwrScheduleId,
    lwr.LwrStatus,
    lwr.LwrPurpose,
    lwr.LwrRemarks,
    lwr.LwrTakenBy,
    lwr.LwrUpdatedOn,
    lwr.LwrFuncLocId,
    lwr.LwrMovId,
    lwr.wheelhistflag
FROM LocoWheelRegister AS lwr
INNER JOIN LocoMaster AS lm
    ON lm.LomId = lwr.LwrLocoId
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
