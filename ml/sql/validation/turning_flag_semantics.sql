-- Turning-flag semantics validation.
--
-- Question (degradation_semantics.md §4): what does wsmturning1/2 = 1 mean?
--   (a) event at THIS measurement (turning happened here), or
--   (b) cumulative state ("this wheel has been turned", persists)?
--
-- Test 1 (flag persistence): if (b), once the flag is 1 it should stay 1 on
--   every later row for the same equipment. If (a), 1 should appear on isolated
--   rows and drop back to 0 on the following row.
-- Test 2 (diameter around turning): does diameter increase (reprofiling restores
--   profile) or decrease right after a flagged turning row?
-- Test 3 (side agreement): wsmturning1 vs wsmturning2.
-- Test 4 (skid relationship): wsmturning1 vs wsmSkidTurn1.
--
-- Read-only. Source snapshot: SLAM_PROD_DB_10.05.2022, 2026-08-03.

-- ---------------------------------------------------------------------------
-- TEST 1a: consecutive-row flag persistence per equipment.
-- Count, for each equipment, whether a wsmturning1=1 row is immediately
-- followed by another wsmturning1=1 row (persistent) or by a 0 (event).
-- ---------------------------------------------------------------------------
WITH ordered AS (
    SELECT
        wsmEquipmentId,
        wsmUpdatedOn,
        wsmturning1,
        wsmturning2,
        LEAD(wsmturning1) OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS next_turn1,
        LEAD(wsmturning2) OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS next_turn2
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
)
SELECT
    CASE
        WHEN wsmturning1 = 1 AND next_turn1 = 1 THEN 'turn1 followed by turn1 (state)'
        WHEN wsmturning1 = 1 AND next_turn1 = 0 THEN 'turn1 followed by 0 (event)'
        WHEN wsmturning1 = 1 AND next_turn1 IS NULL THEN 'turn1 is last row'
        ELSE 'not a turning row'
    END AS pattern,
    COUNT(*) AS n
FROM ordered
GROUP BY CASE
        WHEN wsmturning1 = 1 AND next_turn1 = 1 THEN 'turn1 followed by turn1 (state)'
        WHEN wsmturning1 = 1 AND next_turn1 = 0 THEN 'turn1 followed by 0 (event)'
        WHEN wsmturning1 = 1 AND next_turn1 IS NULL THEN 'turn1 is last row'
        ELSE 'not a turning row'
    END
ORDER BY n DESC;

-- ---------------------------------------------------------------------------
-- TEST 1c: does a wsmturning1=1 row share an equipment with any OTHER
-- wsmturning1=1 row (i.e., can the same wheelset be turned more than once)?
-- ---------------------------------------------------------------------------
WITH equipment_turn_counts AS (
    SELECT
        wsmEquipmentId,
        SUM(CASE WHEN wsmturning1 = 1 THEN 1 ELSE 0 END) AS turn1_count,
        SUM(CASE WHEN wsmturning2 = 1 THEN 1 ELSE 0 END) AS turn2_count
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
    GROUP BY wsmEquipmentId
)
SELECT
    'equipment_with_turn1' AS metric,
    COUNT(*) AS value
FROM equipment_turn_counts
WHERE turn1_count > 0
UNION ALL
SELECT 'equipment_with_multiple_turn1', COUNT(*)
FROM equipment_turn_counts
WHERE turn1_count > 1
UNION ALL
SELECT 'equipment_with_multiple_turn2', COUNT(*)
FROM equipment_turn_counts
WHERE turn2_count > 1
UNION ALL
SELECT 'equipment_with_any_turn2', COUNT(*)
FROM equipment_turn_counts
WHERE turn2_count > 0;

-- ---------------------------------------------------------------------------
-- TEST 1d: per-equipment distribution of turn1 events.
-- ---------------------------------------------------------------------------
SELECT turn1_count, COUNT(*) AS n_equipment
FROM (
    SELECT
        wsmEquipmentId,
        SUM(CASE WHEN wsmturning1 = 1 THEN 1 ELSE 0 END) AS turn1_count
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
    GROUP BY wsmEquipmentId
) t
WHERE turn1_count > 0
GROUP BY turn1_count
ORDER BY turn1_count DESC;

-- ---------------------------------------------------------------------------
-- TEST 1b: after a turning row, what does the NEXT row's flag show?
-- event-vs-state discriminator (detailed, includes row gap).
-- ---------------------------------------------------------------------------
WITH ordered AS (
    SELECT
        wsmEquipmentId,
        wsmUpdatedOn,
        wsmturning1,
        wsmturning2,
        LEAD(wsmturning1) OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS next_turn1,
        LEAD(wsmturning2) OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS next_turn2
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
)
SELECT
    CASE
        WHEN wsmturning1 = 1 AND next_turn1 = 1 THEN 'turn1 followed by turn1 (state)'
        WHEN wsmturning1 = 1 AND next_turn1 = 0 THEN 'turn1 followed by 0 (event)'
        WHEN wsmturning1 = 1 AND next_turn1 IS NULL THEN 'turn1 is last row'
        ELSE 'not a turning row'
    END AS pattern,
    COUNT(*) AS n
FROM ordered
GROUP BY CASE
        WHEN wsmturning1 = 1 AND next_turn1 = 1 THEN 'turn1 followed by turn1 (state)'
        WHEN wsmturning1 = 1 AND next_turn1 = 0 THEN 'turn1 followed by 0 (event)'
        WHEN wsmturning1 = 1 AND next_turn1 IS NULL THEN 'turn1 is last row'
        ELSE 'not a turning row'
    END
ORDER BY n DESC;

-- ---------------------------------------------------------------------------
-- TEST 2: diameter behavior across a turning row (before -> at -> after).
-- ---------------------------------------------------------------------------
WITH ordered AS (
    SELECT
        wsmEquipmentId,
        wsmUpdatedOn,
        wsmDia1,
        wsmDia2,
        wsmRoot1,
        wsmturning1,
        ROW_NUMBER() OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS rn
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
),
pairs AS (
    SELECT
        o.wsmEquipmentId,
        o.wsmUpdatedOn AS cur_date,
        p.wsmUpdatedOn AS prev_date,
        o.wsmturning1 AS cur_turn,
        p.wsmturning1 AS prev_turn,
        o.wsmDia1 AS cur_dia,
        p.wsmDia1 AS prev_dia,
        o.wsmDia2 AS cur_dia2,
        p.wsmDia2 AS prev_dia2,
        o.wsmRoot1 AS cur_root,
        p.wsmRoot1 AS prev_root,
        DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) AS days_gap
    FROM ordered o
    JOIN ordered p ON o.wsmEquipmentId = p.wsmEquipmentId AND p.rn = o.rn - 1
    WHERE o.wsmUpdatedOn > p.wsmUpdatedOn
)
SELECT
    CASE
        WHEN cur_turn = 1 THEN 'interval ENDS at turning row'
        WHEN prev_turn = 1 THEN 'interval STARTS at turning row'
        ELSE 'no turning'
    END AS interval_type,
    COUNT(*) AS n,
    ROUND(AVG(cur_dia - prev_dia), 3) AS avg_dia1_delta,
    ROUND(AVG(cur_dia2 - prev_dia2), 3) AS avg_dia2_delta,
    ROUND(AVG(cur_root - prev_root), 3) AS avg_root_delta,
    SUM(CASE WHEN cur_dia > prev_dia THEN 1 ELSE 0 END) AS dia1_increased,
    SUM(CASE WHEN cur_dia < prev_dia THEN 1 ELSE 0 END) AS dia1_decreased,
    ROUND(AVG(days_gap), 1) AS avg_days_gap
FROM pairs
WHERE cur_dia IS NOT NULL AND prev_dia IS NOT NULL
  AND cur_dia BETWEEN 600 AND 1300 AND prev_dia BETWEEN 600 AND 1300
  AND days_gap BETWEEN 1 AND 400
GROUP BY CASE
        WHEN cur_turn = 1 THEN 'interval ENDS at turning row'
        WHEN prev_turn = 1 THEN 'interval STARTS at turning row'
        ELSE 'no turning'
    END
ORDER BY interval_type;

-- ---------------------------------------------------------------------------
-- TEST 3: wsmturning1 vs wsmturning2 agreement.
-- ---------------------------------------------------------------------------
SELECT
    wsmturning1,
    wsmturning2,
    COUNT(*) AS n
FROM WheelSetMeasurements
WHERE wsmEquipmentId IS NOT NULL
GROUP BY wsmturning1, wsmturning2
ORDER BY wsmturning1, wsmturning2;

-- ---------------------------------------------------------------------------
-- TEST 4: wsmturning1 vs wsmSkidTurn1 relationship.
-- ---------------------------------------------------------------------------
SELECT
    wsmturning1,
    wsmSkidTurn1,
    COUNT(*) AS n
FROM WheelSetMeasurements
WHERE wsmEquipmentId IS NOT NULL
GROUP BY wsmturning1, wsmSkidTurn1
ORDER BY wsmturning1, wsmSkidTurn1;

-- ---------------------------------------------------------------------------
-- TEST 5: date gap between consecutive turn1=1 rows.
-- Distinguishes repeat turnings (real, separated in time) from same-day
-- duplicate entry rows.
-- ---------------------------------------------------------------------------
WITH ordered AS (
    SELECT wsmEquipmentId, wsmUpdatedOn, wsmturning1,
           ROW_NUMBER() OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS rn
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
)
SELECT
    CASE
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) = 0 THEN 'same_day'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) BETWEEN 1 AND 30 THEN '1-30d'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) BETWEEN 31 AND 180 THEN '31-180d'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) > 180 THEN '>180d'
        ELSE 'other'
    END AS gap_bucket,
    COUNT(*) AS n
FROM ordered o
JOIN ordered p ON o.wsmEquipmentId = p.wsmEquipmentId AND p.rn = o.rn - 1
WHERE o.wsmturning1 = 1 AND p.wsmturning1 = 1
GROUP BY CASE
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) = 0 THEN 'same_day'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) BETWEEN 1 AND 30 THEN '1-30d'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) BETWEEN 31 AND 180 THEN '31-180d'
        WHEN DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) > 180 THEN '>180d'
        ELSE 'other'
    END
ORDER BY n DESC;

-- ---------------------------------------------------------------------------
-- TEST 6: distinct turning DAYS per equipment (event count, deduping same-day).
-- ---------------------------------------------------------------------------
SELECT
    SUM(turn_days) AS total_turn_days,
    SUM(CASE WHEN turn_days > 1 THEN 1 ELSE 0 END) AS equipment_with_multiple_turn_days
FROM (
    SELECT wsmEquipmentId, COUNT(DISTINCT CAST(wsmUpdatedOn AS date)) AS turn_days
    FROM WheelSetMeasurements
    WHERE wsmturning1 = 1
    GROUP BY wsmEquipmentId
) t;

-- ---------------------------------------------------------------------------
-- TEST 7: diameter behaviour at the turning row (cur=1, prev=0).
-- Is diameter restored/increased by turning (semantics-doc assumption) or
-- reduced by material removal?
-- ---------------------------------------------------------------------------
WITH ordered AS (
    SELECT wsmEquipmentId, wsmUpdatedOn, wsmDia1, wsmRoot1, wsmturning1,
           ROW_NUMBER() OVER (PARTITION BY wsmEquipmentId ORDER BY wsmUpdatedOn) AS rn
    FROM WheelSetMeasurements
    WHERE wsmEquipmentId IS NOT NULL
)
SELECT
    CASE
        WHEN (o.wsmDia1 - p.wsmDia1) < -3 THEN 'dia_drop_gt_3'
        WHEN (o.wsmDia1 - p.wsmDia1) BETWEEN -3 AND -0.1 THEN 'dia_drop_0_3'
        WHEN ABS(o.wsmDia1 - p.wsmDia1) <= 0.1 THEN 'dia_same'
        WHEN (o.wsmDia1 - p.wsmDia1) BETWEEN 0.1 AND 3 THEN 'dia_gain_0_3'
        WHEN (o.wsmDia1 - p.wsmDia1) > 3 THEN 'dia_gain_gt_3'
        ELSE 'other'
    END AS bucket,
    COUNT(*) AS n
FROM ordered o
JOIN ordered p ON o.wsmEquipmentId = p.wsmEquipmentId AND p.rn = o.rn - 1
WHERE o.wsmturning1 = 1 AND (p.wsmturning1 = 0 OR p.wsmturning1 IS NULL)
  AND o.wsmDia1 IS NOT NULL AND p.wsmDia1 IS NOT NULL
  AND o.wsmDia1 BETWEEN 600 AND 1300 AND p.wsmDia1 BETWEEN 600 AND 1300
  AND DATEDIFF(day, p.wsmUpdatedOn, o.wsmUpdatedOn) BETWEEN 1 AND 400
GROUP BY CASE
        WHEN (o.wsmDia1 - p.wsmDia1) < -3 THEN 'dia_drop_gt_3'
        WHEN (o.wsmDia1 - p.wsmDia1) BETWEEN -3 AND -0.1 THEN 'dia_drop_0_3'
        WHEN ABS(o.wsmDia1 - p.wsmDia1) <= 0.1 THEN 'dia_same'
        WHEN (o.wsmDia1 - p.wsmDia1) BETWEEN 0.1 AND 3 THEN 'dia_gain_0_3'
        WHEN (o.wsmDia1 - p.wsmDia1) > 3 THEN 'dia_gain_gt_3'
        ELSE 'other'
    END
ORDER BY n DESC;
