-- Identify candidate locomotive shed in/out event ledgers and their join/time fields.
SELECT t.name AS table_name, c.column_id, c.name AS column_name,
       ty.name AS data_type, c.max_length
FROM sys.tables AS t
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE (t.name LIKE '%shed%' OR c.name LIKE '%shed%')
  AND (c.name LIKE '%loco%' OR c.name LIKE '%date%' OR c.name LIKE '%time%' OR c.name LIKE '%in%' OR c.name LIKE '%out%' OR c.name LIKE '%station%')
ORDER BY t.name, c.column_id;
