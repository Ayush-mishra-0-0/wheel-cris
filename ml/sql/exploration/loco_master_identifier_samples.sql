-- Reconciliation evidence: first 1,000 distinct nonblank SLAM locomotive identifiers.
SELECT TOP (1000)
    LomNumber AS loco_master_number,
    LEN(LomNumber) AS source_length
FROM LocoMaster
WHERE NULLIF(LTRIM(RTRIM(LomNumber)), '') IS NOT NULL
GROUP BY LomNumber
ORDER BY LomNumber;
