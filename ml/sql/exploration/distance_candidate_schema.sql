-- Candidate schema only; this is intentionally separate from a semantic claim.
SELECT
    t.name AS table_name,
    c.column_id,
    c.name AS column_name,
    ty.name AS data_type,
    c.max_length,
    c.is_nullable
FROM sys.tables AS t
INNER JOIN sys.columns AS c ON c.object_id = t.object_id
INNER JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
WHERE t.name IN ('MovementRegister', 'RTISLOCOKM', 'DailyOverdueLocoCount', 'MaintenanaceScheduleMaster')
ORDER BY t.name, c.column_id;
