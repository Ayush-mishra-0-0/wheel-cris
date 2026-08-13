-- Wheel/equipment/locomotive validation: identity, cardinality and static
-- coverage. This is intentionally read-only and produces auditable metrics.
WITH measurement_equipment AS (
    SELECT DISTINCT CAST(wsmEquipmentId AS bigint) AS equipment_id
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
), assignments AS (
    SELECT
        CAST(LoeEquipmentMasterRegister AS bigint) AS equipment_id,
        CAST(LoeLocoMaster AS bigint) AS locomotive_id,
        LoeProvisionDate AS provision_date,
        LoeStatus AS assignment_status,
        LoeId AS assignment_id
    FROM LocoEquipments
    WHERE LoeEquipmentMasterRegister IS NOT NULL
), assignment_stats AS (
    SELECT
        equipment_id,
        COUNT(*) AS assignment_count,
        COUNT(DISTINCT locomotive_id) AS distinct_locomotive_count,
        SUM(CASE WHEN provision_date IS NULL OR provision_date IN ('1900-01-01', '1899-12-30') THEN 1 ELSE 0 END) AS missing_provision_date_count
    FROM assignments
    GROUP BY equipment_id
)
SELECT 'measurement_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value
FROM WheelSetMeasurements
UNION ALL
SELECT 'measurements_with_equipment_id', CAST(COUNT_BIG(*) AS decimal(19,2))
FROM WheelSetMeasurements WHERE wsmEquipmentId IS NOT NULL
UNION ALL
SELECT 'measurement_equipment_ids', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurement_equipment
UNION ALL
SELECT 'measurement_equipment_ids_in_equipment_master', CAST(COUNT_BIG(*) AS decimal(19,2))
FROM measurement_equipment AS m INNER JOIN EquipmentMasterRegister AS e ON e.EmrId = m.equipment_id
UNION ALL
SELECT 'measurement_equipment_ids_with_loco_assignment', CAST(COUNT_BIG(*) AS decimal(19,2))
FROM measurement_equipment AS m INNER JOIN assignment_stats AS a ON a.equipment_id = m.equipment_id
UNION ALL
SELECT 'assignment_rows', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM assignments
UNION ALL
SELECT 'assigned_equipment_ids', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM assignment_stats
UNION ALL
SELECT 'equipment_with_multiple_assignment_rows', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM assignment_stats WHERE assignment_count > 1
UNION ALL
SELECT 'equipment_with_multiple_locomotives', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM assignment_stats WHERE distinct_locomotive_count > 1
UNION ALL
SELECT 'assignment_rows_missing_provision_date', CAST(COALESCE(SUM(missing_provision_date_count), 0) AS decimal(19,2)) FROM assignment_stats;
