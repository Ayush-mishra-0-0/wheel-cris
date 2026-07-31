-- Full schemas for the candidate temporal assignment sources.
SELECT
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_NAME IN (
    'LocoEquipmentsHistory',
    'LocoEquipmentChangeRegister',
    'EquipmentHistory',
    'EquipmentTransfer',
    'POHLocoEquipmentChange'
)
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
