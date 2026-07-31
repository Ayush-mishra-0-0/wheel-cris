-- Emergency-event uniqueness and structural validity for the cohort extract.
SELECT 'emergency_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS metric_value FROM INTEG_rtisLocoEmergencyData AS e
INNER JOIN LocoMaster AS lm ON lm.LomNumber = e.LOCO_NO
INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}'
UNION ALL
SELECT 'duplicate_irled_id_rows', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM (
    SELECT e.IrledId FROM INTEG_rtisLocoEmergencyData AS e
    INNER JOIN LocoMaster AS lm ON lm.LomNumber = e.LOCO_NO
    INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
    GROUP BY e.IrledId HAVING COUNT(*) > 1
) AS duplicates
UNION ALL
SELECT 'missing_transmission_time_rows', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM INTEG_rtisLocoEmergencyData AS e
INNER JOIN LocoMaster AS lm ON lm.LomNumber = e.LOCO_NO
INNER JOIN LocoTypes AS lt ON lt.LotId = lm.LomType
WHERE lt.LotTypeName = '{{COHORT}}' AND e.EVENT_TRANSMISSION_TIME IS NULL;
