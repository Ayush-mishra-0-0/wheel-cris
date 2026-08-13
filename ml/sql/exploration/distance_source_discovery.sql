-- Read-only catalogue search for possible locomotive distance/movement sources.
-- This does not assume that a column containing "km" is physical mileage.
SELECT
    s.name COLLATE DATABASE_DEFAULT AS schema_name,
    t.name COLLATE DATABASE_DEFAULT AS table_name,
    c.column_id,
    c.name COLLATE DATABASE_DEFAULT AS column_name,
    ty.name COLLATE DATABASE_DEFAULT AS data_type,
    c.max_length,
    CASE WHEN c.is_nullable = 1 THEN 'nullable' ELSE 'not_null' END AS nullability,
    'table_column' COLLATE DATABASE_DEFAULT AS evidence_type
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE c.name LIKE '%[Kk][Mm]%'
   OR c.name LIKE '%[Dd]istance%'
   OR c.name LIKE '%[Mm]ileage%'
   OR c.name LIKE '%[Oo]dometer%'
   OR c.name LIKE '%[Cc]hainage%'
   OR c.name LIKE '%[Ll]atitude%'
   OR c.name LIKE '%[Ll]ongitude%'
   OR c.name LIKE '%[Gg]ps%'
UNION ALL
SELECT
    SCHEMA_NAME(o.schema_id) COLLATE DATABASE_DEFAULT,
    o.name COLLATE DATABASE_DEFAULT,
    NULL,
    NULL,
    o.type_desc COLLATE DATABASE_DEFAULT,
    NULL,
    NULL,
    'programmable_object_referencing_rtis_distance' COLLATE DATABASE_DEFAULT
FROM sys.sql_modules AS m
INNER JOIN sys.objects AS o ON o.object_id = m.object_id
WHERE m.definition LIKE '%RlkdTotalDistance%'
   OR m.definition LIKE '%RtisLocoKmDetails%'
ORDER BY evidence_type, schema_name, table_name, column_id;
