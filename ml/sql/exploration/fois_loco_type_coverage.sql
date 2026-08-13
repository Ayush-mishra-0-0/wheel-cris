-- Explain FOIS coverage after its successful master-ID reconciliation.
-- Shows whether a zero WAP7 result is an identifier issue or simply source
-- coverage for other locomotive types.
WITH matched AS (
    SELECT
        f.IntgFLidHis,
        f.LocoNumb,
        lm.LomId,
        lt.LotTypeName
    FROM FOIS_LocoLocation_History AS f
    INNER JOIN LocoMaster AS lm
        ON lm.LomNumber = f.LocoNumb
    INNER JOIN LocoTypes AS lt
        ON lt.LotId = lm.LomType
)
SELECT
    LotTypeName AS locomotive_type,
    COUNT_BIG(*) AS fois_rows,
    COUNT(DISTINCT LomId) AS locomotives,
    COUNT(DISTINCT LocoNumb) AS distinct_fois_identifiers
FROM matched
GROUP BY LotTypeName
ORDER BY fois_rows DESC;
