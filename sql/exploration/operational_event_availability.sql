-- Read-only availability check for the operational sources.
-- This confirms whether detailed event fields exist in SQL Server; it does not
-- extract the underlying operational history.
SELECT
    c.TABLE_NAME AS SourceTable,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_NAME IN ('RtisLocoKmDetails', 'INTEG_rtisLocoEmergencyData', 'FOIS_LocoLocation_History')
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
