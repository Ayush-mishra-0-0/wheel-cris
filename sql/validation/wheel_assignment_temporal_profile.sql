-- Effective-date evidence. LocoEquipments has provision dates but no confirmed
-- removal-date field, so this report measures whether a safe temporal interval
-- can be inferred and identifies ambiguous assignment histories.
WITH assignments AS (
    SELECT
        CAST(LoeEquipmentMasterRegister AS bigint) AS equipment_id,
        CAST(LoeLocoMaster AS bigint) AS locomotive_id,
        LoeId AS assignment_id,
        LoeProvisionDate AS provision_date,
        LoeStatus AS assignment_status,
        LEAD(LoeProvisionDate) OVER (
            PARTITION BY LoeEquipmentMasterRegister
            ORDER BY LoeProvisionDate, LoeId
        ) AS next_provision_date,
        LEAD(LoeLocoMaster) OVER (
            PARTITION BY LoeEquipmentMasterRegister
            ORDER BY LoeProvisionDate, LoeId
        ) AS next_locomotive_id
    FROM LocoEquipments
    WHERE LoeEquipmentMasterRegister IS NOT NULL
), classified AS (
    SELECT *,
        CASE
            WHEN provision_date IS NULL OR provision_date IN ('1900-01-01', '1899-12-30') THEN 'missing_provision_date'
            WHEN next_provision_date IS NOT NULL AND next_provision_date <= provision_date THEN 'non_increasing_provision_date'
            WHEN next_locomotive_id IS NOT NULL AND next_locomotive_id = locomotive_id THEN 'repeat_same_locomotive_assignment'
            WHEN next_locomotive_id IS NOT NULL AND next_locomotive_id <> locomotive_id THEN 'locomotive_transfer_candidate'
            ELSE 'latest_or_single_assignment'
        END AS temporal_class
    FROM assignments
)
SELECT
    temporal_class,
    COUNT_BIG(*) AS assignment_rows,
    COUNT(DISTINCT equipment_id) AS equipment_ids
FROM classified
GROUP BY temporal_class
ORDER BY temporal_class;
