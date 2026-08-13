-- Identify timestamp columns before inspecting large event tables.
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN (
    'RTIS_LocoKmDetails',
    'FOIS_LocoLocation_History',
    'EmergencyData'
)
ORDER BY TABLE_NAME, ORDINAL_POSITION;
