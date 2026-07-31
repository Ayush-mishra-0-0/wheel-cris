-- Locate candidate history/transfer/audit sources for temporal wheel/equipment
-- assignment. Candidates must expose equipment and locomotive identifiers plus
-- an event/effective timestamp before they can close the validation gap.
WITH catalogue AS (
    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
), table_candidates AS (
    SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME
    FROM catalogue
    WHERE LOWER(TABLE_NAME) LIKE '%locoequip%'
       OR LOWER(TABLE_NAME) LIKE '%equipment%history%'
       OR LOWER(TABLE_NAME) LIKE '%equipment%transfer%'
       OR LOWER(TABLE_NAME) LIKE '%equipment%movement%'
       OR LOWER(TABLE_NAME) LIKE '%assignment%'
       OR LOWER(TABLE_NAME) LIKE '%provision%'
       OR LOWER(TABLE_NAME) LIKE '%transaction%'
       OR LOWER(TABLE_NAME) LIKE '%audit%'
       OR LOWER(COLUMN_NAME) LIKE '%loeequipmentmasterregister%'
       OR LOWER(COLUMN_NAME) LIKE '%loelocomaster%'
), relevant_columns AS (
    SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE
    FROM catalogue AS c
    INNER JOIN table_candidates AS t
        ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
    WHERE LOWER(c.COLUMN_NAME) LIKE '%equipment%'
       OR LOWER(c.COLUMN_NAME) LIKE '%loco%'
       OR LOWER(c.COLUMN_NAME) LIKE '%provision%'
       OR LOWER(c.COLUMN_NAME) LIKE '%transfer%'
       OR LOWER(c.COLUMN_NAME) LIKE '%movement%'
       OR LOWER(c.COLUMN_NAME) LIKE '%created%'
       OR LOWER(c.COLUMN_NAME) LIKE '%modified%'
       OR LOWER(c.COLUMN_NAME) LIKE '%date%'
       OR LOWER(c.COLUMN_NAME) LIKE '%time%'
       OR LOWER(c.COLUMN_NAME) LIKE '%status%'
)
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM relevant_columns
ORDER BY TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME;
