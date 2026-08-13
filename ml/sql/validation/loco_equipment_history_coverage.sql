-- Initial coverage/profile for the primary effective-dated candidate source.
WITH measurement_equipment AS (
    SELECT DISTINCT CAST(wsmEquipmentId AS bigint) AS equipment_id
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
), history AS (
    SELECT
        CAST(LoehEquipmentMasterRegister AS bigint) AS equipment_id,
        CAST(LoehLocoMaster AS bigint) AS locomotive_id,
        LoehProvisionDate AS provision_date,
        LoehRemovedDate AS removed_date,
        LoehStatus AS assignment_status
    FROM LocoEquipmentsHistory
    WHERE LoehEquipmentMasterRegister IS NOT NULL
)
SELECT 'history_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM history
UNION ALL SELECT 'history_equipment_ids', CAST(COUNT_BIG(DISTINCT equipment_id) AS decimal(19,2)) FROM history
UNION ALL SELECT 'measurement_equipment_ids_with_history', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurement_equipment AS m INNER JOIN (SELECT DISTINCT equipment_id FROM history) AS h ON h.equipment_id = m.equipment_id
UNION ALL SELECT 'history_rows_with_locomotive', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM history WHERE locomotive_id IS NOT NULL
UNION ALL SELECT 'history_rows_with_valid_provision_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM history WHERE provision_date IS NOT NULL AND provision_date NOT IN ('1900-01-01', '1899-12-30')
UNION ALL SELECT 'history_rows_with_valid_removed_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM history WHERE removed_date IS NOT NULL AND removed_date NOT IN ('1900-01-01', '1899-12-30')
UNION ALL SELECT 'history_rows_with_invalid_date_order', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM history WHERE provision_date IS NOT NULL AND removed_date IS NOT NULL AND removed_date < provision_date;
