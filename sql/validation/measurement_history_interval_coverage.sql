-- Temporal match evidence using LocoEquipmentsHistory. A candidate interval is
-- [provision_date, removed_date] or open-ended when removal is absent. This
-- report measures ambiguity; it does not silently choose one overlapping row.
WITH measurements AS (
    SELECT wsmId AS measurement_id, CAST(wsmEquipmentId AS bigint) AS equipment_id, wsmUpdatedOn AS measurement_timestamp
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL AND wsmUpdatedOn IS NOT NULL
), history AS (
    SELECT CAST(LoehEquipmentMasterRegister AS bigint) AS equipment_id, LoehProvisionDate AS provision_date, LoehRemovedDate AS removed_date
    FROM LocoEquipmentsHistory
    WHERE LoehEquipmentMasterRegister IS NOT NULL
      AND LoehProvisionDate IS NOT NULL
      AND LoehProvisionDate NOT IN ('1900-01-01', '1899-12-30')
      AND (LoehRemovedDate IS NULL OR LoehRemovedDate NOT IN ('1900-01-01', '1899-12-30'))
      AND (LoehRemovedDate IS NULL OR LoehRemovedDate >= LoehProvisionDate)
), candidates AS (
    SELECT m.measurement_id, COUNT(h.equipment_id) AS candidate_interval_count
    FROM measurements AS m
    LEFT JOIN history AS h
        ON h.equipment_id = m.equipment_id
       AND m.measurement_timestamp >= h.provision_date
       AND (h.removed_date IS NULL OR m.measurement_timestamp <= h.removed_date)
    GROUP BY m.measurement_id
)
SELECT 'measurements_evaluated' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM candidates
UNION ALL SELECT 'measurements_with_no_history_interval', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM candidates WHERE candidate_interval_count = 0
UNION ALL SELECT 'measurements_with_one_history_interval', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM candidates WHERE candidate_interval_count = 1
UNION ALL SELECT 'measurements_with_multiple_history_intervals', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM candidates WHERE candidate_interval_count > 1;
