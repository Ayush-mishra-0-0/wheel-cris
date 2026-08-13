-- Bronze/raw equipment-failure extract: abnormal-equipment failures linked to a
-- locomotive via LocoEquipmentChangeRegister. Cohort-filtered via LocoMaster.
SELECT
    e.EfrId,
    e.EfrLocoChangeRegister,
    l.LerLocoMaster AS LocoId,
    l.LerPositionId,
    e.EfrDateofFailure,
    e.EfrUpdatedOn,
    e.EfrAbnormality,
    e.EfrReasonsForAbnormality,
    e.EfrFailureCause,
    e.EfrActionTaken,
    e.EfrRemarks,
    e.EfrCategory,
    e.EfrRepairSheet,
    e.EfrStatisticalFailure,
    e.EfrRootCause,
    e.EfrPreventiveAction,
    e.EfrResponsibility,
    e.EfrAttendedBy
FROM EquipmentFailureRegister AS e
INNER JOIN LocoEquipmentChangeRegister AS l
    ON l.LerId = e.EfrLocoChangeRegister
INNER JOIN LocoMaster AS lm
    ON lm.LomId = l.LerLocoMaster
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
