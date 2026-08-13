-- Bronze/raw equipment-change extract: equipment provision/removal on a
-- locomotive. Primary wheel-age proxy (LerProvidedOn) and replacement evidence.
-- Cohort-filtered via LocoMaster.
SELECT
    l.LerId,
    l.LerLocoMaster,
    l.LerScheduleTypes,
    l.LerOldEquipmentMasterRegister,
    l.LerPositionId,
    l.LerDateOfRemoval,
    l.LerCauseOfRemoval,
    l.LerNewEquipmentMasterRegister,
    l.LerProvidedOn,
    l.LerRemarks,
    l.LerAbnormality,
    l.LerPOH,
    l.LerOnLocoAttn,
    l.LerCreatedOn,
    l.LerLastModifiedOn,
    l.LerParentEquiment,
    l.LerFunctionalLocation,
    l.LerStatus,
    l.LerUnderWarranty
FROM LocoEquipmentChangeRegister AS l
INNER JOIN LocoMaster AS lm
    ON lm.LomId = l.LerLocoMaster
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
