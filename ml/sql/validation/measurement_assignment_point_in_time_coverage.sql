-- Row-weighted point-in-time coverage for measurements. Because the currently
-- discovered LocoEquipments table has one row per equipment ID, this evaluates
-- its provision-date condition but does not claim a historical removal date.
WITH measurements AS (
    SELECT wsmId AS measurement_id, CAST(wsmEquipmentId AS bigint) AS equipment_id, wsmUpdatedOn AS measurement_timestamp
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
), assignments AS (
    SELECT CAST(LoeEquipmentMasterRegister AS bigint) AS equipment_id, CAST(LoeLocoMaster AS bigint) AS locomotive_id, LoeProvisionDate AS provision_date
    FROM LocoEquipments
    WHERE LoeEquipmentMasterRegister IS NOT NULL
)
SELECT 'measurements_with_equipment_id' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM measurements
UNION ALL
SELECT 'measurements_with_assignment_row', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurements AS m INNER JOIN assignments AS a ON a.equipment_id = m.equipment_id
UNION ALL
SELECT 'measurements_with_valid_provision_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurements AS m INNER JOIN assignments AS a ON a.equipment_id = m.equipment_id WHERE a.provision_date IS NOT NULL AND a.provision_date NOT IN ('1900-01-01', '1899-12-30')
UNION ALL
SELECT 'measurements_on_or_after_provision_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurements AS m INNER JOIN assignments AS a ON a.equipment_id = m.equipment_id WHERE a.provision_date IS NOT NULL AND a.provision_date NOT IN ('1900-01-01', '1899-12-30') AND m.measurement_timestamp >= a.provision_date
UNION ALL
SELECT 'measurements_before_provision_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurements AS m INNER JOIN assignments AS a ON a.equipment_id = m.equipment_id WHERE a.provision_date IS NOT NULL AND a.provision_date NOT IN ('1900-01-01', '1899-12-30') AND m.measurement_timestamp < a.provision_date
UNION ALL
SELECT 'measurements_with_missing_or_sentinel_provision_date', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM measurements AS m INNER JOIN assignments AS a ON a.equipment_id = m.equipment_id WHERE a.provision_date IS NULL OR a.provision_date IN ('1900-01-01', '1899-12-30');
