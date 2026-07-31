-- Inspect FOIS-specific master/cross-reference candidates returned by the
-- catalogue search, before selecting a future join path.
SELECT
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_NAME IN ('foislocomaster', 'foislocomasterDetails', 'foislocoshedout', 'foisshedin')
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
