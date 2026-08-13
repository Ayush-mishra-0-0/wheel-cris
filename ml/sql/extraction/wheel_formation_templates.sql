-- Bronze/raw wheel-formation reference: maps wheelset position (1-6) + end type
-- (1/2) to physical wheel position (1-12). Cohort-filtered via LocoTypes.
SELECT
    wft.WftId,
    wft.WftLotId,
    lt.LotTypeName AS LocoType,
    wft.WftWSPos,
    wft.WftEndType,
    wft.WftWheelPos
FROM WheelFormationTemplates AS wft
INNER JOIN LocoTypes AS lt
    ON lt.LotId = wft.WftLotId
WHERE lt.LotTypeName = '{{COHORT}}';
