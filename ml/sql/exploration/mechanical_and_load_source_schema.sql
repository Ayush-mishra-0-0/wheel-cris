-- Read-only schema check for candidate mechanical-configuration and
-- train/load sources discovered in the SQL Server catalogue.
SELECT
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.TABLE_NAME IN (
    'LocoEquipments', 'BogieTypes', 'SuspensionTypes',
    'INTEG_icmsLocoTrainAttachmentDetail',
    'view_locolocation_trackhistory'
)
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION;
