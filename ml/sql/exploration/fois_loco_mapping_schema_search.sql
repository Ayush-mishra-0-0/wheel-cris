-- Find candidate cross-reference tables: FOIS-aware tables with locomotive
-- fields, or tables that contain both FOIS- and locomotive-named columns.
WITH column_catalogue AS (
    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
), candidates AS (
    SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME
    FROM column_catalogue
    WHERE LOWER(TABLE_NAME) LIKE '%fois%'
       OR LOWER(COLUMN_NAME) LIKE '%fois%'
), loco_fields AS (
    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM column_catalogue
    WHERE LOWER(COLUMN_NAME) LIKE '%loco%'
       OR LOWER(COLUMN_NAME) LIKE '%lom%'
)
SELECT
    l.TABLE_SCHEMA,
    l.TABLE_NAME,
    l.COLUMN_NAME AS loco_related_column,
    l.DATA_TYPE AS loco_related_type
FROM loco_fields AS l
INNER JOIN candidates AS c
    ON c.TABLE_SCHEMA = l.TABLE_SCHEMA AND c.TABLE_NAME = l.TABLE_NAME
ORDER BY l.TABLE_SCHEMA, l.TABLE_NAME, l.COLUMN_NAME;
