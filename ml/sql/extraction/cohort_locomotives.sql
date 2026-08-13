-- Locomotive reference dataset. Experiment filtering happens outside this SQL.
SELECT
    lm.LomId,
    lm.LomNumber,
    lm.LomType,
    lt.LotTypeName AS LocoType,
    lm.LomMake,
    lm.LomDoC AS LomCommissionDate,
    lm.LomStatus
FROM LocoMaster AS lm
INNER JOIN LocoTypes AS lt
    ON lm.LomType = lt.LotId
