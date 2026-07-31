-- Find FOIS/movement-history tables beyond the empty current location table.
SELECT t.name AS table_name, SUM(p.rows) AS row_count
FROM sys.tables AS t
INNER JOIN sys.partitions AS p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
WHERE t.name LIKE '%FOIS%' OR t.name LIKE '%Location%History%' OR t.name LIKE '%TrackHistory%'
GROUP BY t.name
ORDER BY row_count DESC, t.name;
