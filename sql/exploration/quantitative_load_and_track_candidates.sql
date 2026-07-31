-- High-precision follow-up: exclude generic train/axle mentions and surface
-- only fields that plausibly represent quantitative load or track geometry.
SELECT
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE LOWER(c.COLUMN_NAME) LIKE '%weight%'
   OR LOWER(c.COLUMN_NAME) LIKE '%tonnage%'
   OR LOWER(c.COLUMN_NAME) LIKE '%gross%'
   OR LOWER(c.COLUMN_NAME) LIKE '%tare%'
   OR LOWER(c.COLUMN_NAME) LIKE '%axleload%'
   OR LOWER(c.COLUMN_NAME) LIKE '%axle_load%'
   OR LOWER(c.COLUMN_NAME) LIKE '%wheelload%'
   OR LOWER(c.COLUMN_NAME) LIKE '%wheel_load%'
   OR LOWER(c.COLUMN_NAME) LIKE '%curvature%'
   OR LOWER(c.COLUMN_NAME) LIKE '%curve_radius%'
   OR LOWER(c.COLUMN_NAME) LIKE '%gradient%'
   OR LOWER(c.COLUMN_NAME) LIKE '%grade%'
   OR LOWER(c.COLUMN_NAME) LIKE '%chainage%'
   OR LOWER(c.COLUMN_NAME) LIKE '%track_quality%'
   OR LOWER(c.COLUMN_NAME) LIKE '%rail_profile%'
ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION;
