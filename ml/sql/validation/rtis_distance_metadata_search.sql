-- Search SQL Server programmable-object and extended-property metadata for
-- an authoritative definition or query logic involving RlkdTotalDistance.
SELECT 'module' AS evidence_type, OBJECT_SCHEMA_NAME(m.object_id) AS schema_name,
    OBJECT_NAME(m.object_id) AS object_name, o.type_desc AS object_type,
    CAST(m.definition AS varchar(max)) AS evidence_text
FROM sys.sql_modules AS m
INNER JOIN sys.objects AS o ON o.object_id = m.object_id
WHERE m.definition LIKE '%RlkdTotalDistance%'
UNION ALL
SELECT 'extended_property', SCHEMA_NAME(t.schema_id), t.name, 'TABLE',
    CAST(ep.value AS varchar(max))
FROM sys.extended_properties AS ep
INNER JOIN sys.tables AS t ON t.object_id = ep.major_id
WHERE t.name = 'RtisLocoKmDetails';
