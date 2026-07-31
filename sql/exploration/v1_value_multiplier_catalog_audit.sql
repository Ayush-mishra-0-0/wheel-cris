-- Read-only, schema-wide audit for all Version-1 value-multiplier candidates.
-- A match proves only that a candidate column/table exists; follow-on checks
-- must establish grain, coverage, meaning, time field and loco/route linkage.
WITH patterns AS (
    SELECT 'load_axle_weight' AS Domain, '%axle%' AS Pattern UNION ALL
    SELECT 'load_axle_weight', '%load%' UNION ALL
    SELECT 'load_axle_weight', '%weight%' UNION ALL
    SELECT 'load_axle_weight', '%tonnage%' UNION ALL
    SELECT 'load_axle_weight', '%ton%' UNION ALL
    SELECT 'load_axle_weight', '%wagon%' UNION ALL
    SELECT 'load_axle_weight', '%rake%' UNION ALL
    SELECT 'load_axle_weight', '%coach%' UNION ALL
    SELECT 'load_axle_weight', '%train%' UNION ALL
    SELECT 'track_geometry', '%curve%' UNION ALL
    SELECT 'track_geometry', '%radius%' UNION ALL
    SELECT 'track_geometry', '%gradient%' UNION ALL
    SELECT 'track_geometry', '%grade%' UNION ALL
    SELECT 'track_geometry', '%chainage%' UNION ALL
    SELECT 'track_geometry', '%track%' UNION ALL
    SELECT 'track_geometry', '%rail%' UNION ALL
    SELECT 'track_geometry', '%turnout%' UNION ALL
    SELECT 'track_geometry', '%section%' UNION ALL
    SELECT 'weather_environment', '%weather%' UNION ALL
    SELECT 'weather_environment', '%rain%' UNION ALL
    SELECT 'weather_environment', '%temperature%' UNION ALL
    SELECT 'weather_environment', '%humidity%' UNION ALL
    SELECT 'weather_environment', '%dust%' UNION ALL
    SELECT 'weather_environment', '%wind%' UNION ALL
    SELECT 'sensor_subsystem', '%brake%' UNION ALL
    SELECT 'sensor_subsystem', '%slip%' UNION ALL
    SELECT 'sensor_subsystem', '%slide%' UNION ALL
    SELECT 'sensor_subsystem', '%vibration%' UNION ALL
    SELECT 'sensor_subsystem', '%vib%' UNION ALL
    SELECT 'sensor_subsystem', '%bearing%' UNION ALL
    SELECT 'sensor_subsystem', '%suspension%' UNION ALL
    SELECT 'sensor_subsystem', '%bogie%' UNION ALL
    SELECT 'sensor_subsystem', '%pressure%' UNION ALL
    SELECT 'sensor_subsystem', '%accelerom%' UNION ALL
    SELECT 'sensor_subsystem', '%torque%'
)
SELECT DISTINCT
    p.Domain,
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    'column-name match' AS Evidence
FROM INFORMATION_SCHEMA.COLUMNS AS c
INNER JOIN patterns AS p
    ON LOWER(c.COLUMN_NAME) LIKE p.Pattern

UNION

SELECT DISTINCT
    p.Domain,
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    CAST(NULL AS int),
    CAST(NULL AS varchar(128)),
    CAST(NULL AS varchar(128)),
    CAST(NULL AS varchar(3)),
    'table-name match' AS Evidence
FROM INFORMATION_SCHEMA.TABLES AS t
INNER JOIN patterns AS p
    ON LOWER(t.TABLE_NAME) LIKE p.Pattern
WHERE t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
ORDER BY Domain, TABLE_SCHEMA, TABLE_NAME, Evidence, ORDINAL_POSITION;
