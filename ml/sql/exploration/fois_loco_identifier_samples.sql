-- Reconciliation evidence: first 1,000 distinct nonblank FOIS identifiers.
SELECT TOP (1000)
    LocoNumb AS fois_loco_number,
    LEN(LocoNumb) AS source_length
FROM FOIS_LocoLocation_History
WHERE NULLIF(LTRIM(RTRIM(LocoNumb)), '') IS NOT NULL
GROUP BY LocoNumb
ORDER BY LocoNumb;
