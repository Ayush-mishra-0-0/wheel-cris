-- Read-only discovery for the requested FOIS location source and its columns.
SELECT t.name AS table_name, c.column_id, c.name AS column_name,
    ty.name AS data_type, c.max_length, c.is_nullable
FROM sys.tables AS t
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.name LIKE '%FOIS%LOCO%LOCATION%'
   OR t.name LIKE '%LOCOLOCATION%'
ORDER BY t.name, c.column_id;
