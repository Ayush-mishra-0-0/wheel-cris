-- Locate the exact source-table names before inspecting large event datasets.
SELECT name AS TableName
FROM sys.tables
WHERE name LIKE '%RTIS%'
   OR name LIKE '%FOIS%'
   OR name LIKE '%Emergency%'
ORDER BY name;
