-- Bronze/raw cohort-filtered temporal equipment-to-locomotive assignments.
-- Do not filter by provision date: assignments before the experiment window can
-- still be valid at its beginning.
SELECT
    h.LoehId,
    h.LoehLocoMaster,
    h.LoehProvisionDate,
    h.LoehEquipmentMasterRegister,
    h.LoehLocoEquipmentInfo,
    h.LoehEquipmentType,
    h.LoehEquipmentPositions,
    h.LoehRemovedDate,
    h.LoehStatus,
    h.LoehCreatedOn,
    h.LoehCreatedBy,
    h.LoehModifiedOn,
    h.LoehModifiedBy
FROM LocoEquipmentsHistory AS h
INNER JOIN LocoMaster AS lm
    ON lm.LomId = h.LoehLocoMaster
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
