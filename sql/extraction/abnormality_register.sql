-- Bronze/raw abnormality-register extract: abnormal wheel/equipment events with
-- jobcard link and equipment type/position context. Cohort-filtered via AbrLoco.
SELECT
    a.AbrId,
    a.AbrLoco,
    a.AbrCreatedOn,
    a.AbrAttendedOn,
    a.AbrLastModifiedOn,
    a.AbrCreatedTimeStamp,
    a.AbrDescription,
    a.AbrRemarks,
    a.AbrSubject,
    a.AbrAbnormalityNo,
    a.AbrStatus,
    a.AbrIsolationFlag,
    a.AbrJobcardID,
    a.AbrEqTypeId,
    a.AbrEqPositionID,
    a.AbrEqTypeCode,
    a.AbrEqPosition,
    a.AbrFuncLocation,
    a.AbrFromSection,
    a.AbrToSection,
    a.AbrTLCtransfer,
    a.AbrSjjId,
    a.AbrAtsID,
    a.AbrEqtMake,
    a.AbrCreatedBy,
    a.AbrIdentifiedBy,
    a.AbrClosedBy,
    a.AbrClosingFunction,
    a.AbrLastModifiedBy
FROM AbnormalityRegister AS a
INNER JOIN LocoMaster AS lm
    ON lm.LomId = a.AbrLoco
INNER JOIN LocoTypes AS lt
    ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}';
