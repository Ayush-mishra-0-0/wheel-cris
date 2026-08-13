-- Find candidate traversal, block, signal, section and station-event tables.
SELECT s.name AS schema_name, t.name AS table_name, c.column_id, c.name AS column_name,
    ty.name AS data_type, 'column_candidate' AS evidence_type
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.name LIKE '%[Ss]ection%' OR t.name LIKE '%[Bb]lock%' OR t.name LIKE '%[Ss]ignal%'
   OR c.name LIKE '%[Ss]ection%' OR c.name LIKE '%[Bb]lock%' OR c.name LIKE '%[Ss]ignal%'
   OR c.name LIKE '%[Cc]hainage%' OR c.name LIKE '%[Tt]rack%'
ORDER BY t.name, c.column_id;
