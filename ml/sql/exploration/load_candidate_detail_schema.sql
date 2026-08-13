-- Read-only detail check for the only high-precision quantitative-load
-- candidates found in the schema-wide audit.
SELECT
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_NAME IN ('LocoTypes', 'OMRSLocoDefectDetails')
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
