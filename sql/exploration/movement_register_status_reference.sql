-- Locate any formal relationship or lookup for MovementRegister.MorLomStatus.
SELECT 'foreign_key' AS evidence_type,
    OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS schema_name,
    OBJECT_NAME(fkc.parent_object_id) AS table_name,
    pc.name AS column_name,
    OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS referenced_schema,
    OBJECT_NAME(fkc.referenced_object_id) AS referenced_table,
    rc.name AS referenced_column
FROM sys.foreign_key_columns AS fkc
INNER JOIN sys.columns AS pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
INNER JOIN sys.columns AS rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
WHERE OBJECT_NAME(fkc.parent_object_id) = 'MovementRegister'
  AND pc.name = 'MorLomStatus'
UNION ALL
SELECT 'candidate_lookup', s.name, t.name, c.name, NULL, NULL, NULL
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
WHERE (t.name LIKE '%Loco%Status%' OR t.name LIKE '%Status%')
  AND (c.name LIKE '%Status%' OR c.name LIKE '%Name%' OR c.name LIKE '%Description%')
ORDER BY evidence_type, table_name, column_name;
