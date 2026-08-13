-- Read-only catalogue search for sources supporting the eight engineering
-- domains. Names indicate candidates only; grain, coverage, and joinability
-- still need validation before a source is accepted into Gold.
SELECT DISTINCT
    'table-name candidate' AS EvidenceType,
    t.TABLE_SCHEMA,
    t.TABLE_NAME,
    CAST(NULL AS varchar(128)) AS COLUMN_NAME,
    CAST(NULL AS varchar(128)) AS DATA_TYPE
FROM INFORMATION_SCHEMA.TABLES AS t
WHERE t.TABLE_TYPE = 'BASE TABLE'
  AND (
      t.TABLE_NAME LIKE '%wheel%' OR t.TABLE_NAME LIKE '%equipment%'
      OR t.TABLE_NAME LIKE '%maintenance%' OR t.TABLE_NAME LIKE '%job%'
      OR t.TABLE_NAME LIKE '%defect%' OR t.TABLE_NAME LIKE '%failure%'
      OR t.TABLE_NAME LIKE '%RTIS%' OR t.TABLE_NAME LIKE '%FOIS%'
      OR t.TABLE_NAME LIKE '%route%' OR t.TABLE_NAME LIKE '%track%'
      OR t.TABLE_NAME LIKE '%section%' OR t.TABLE_NAME LIKE '%gradient%'
      OR t.TABLE_NAME LIKE '%curve%' OR t.TABLE_NAME LIKE '%weather%'
      OR t.TABLE_NAME LIKE '%rain%' OR t.TABLE_NAME LIKE '%temperature%'
      OR t.TABLE_NAME LIKE '%load%' OR t.TABLE_NAME LIKE '%wagon%'
      OR t.TABLE_NAME LIKE '%rake%' OR t.TABLE_NAME LIKE '%brake%'
      OR t.TABLE_NAME LIKE '%bogie%' OR t.TABLE_NAME LIKE '%bearing%'
      OR t.TABLE_NAME LIKE '%suspension%' OR t.TABLE_NAME LIKE '%material%'
      OR t.TABLE_NAME LIKE '%steel%'
  )

UNION ALL

SELECT
    'column-name candidate',
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE c.COLUMN_NAME LIKE '%weather%'
   OR c.COLUMN_NAME LIKE '%rain%'
   OR c.COLUMN_NAME LIKE '%temp%'
   OR c.COLUMN_NAME LIKE '%humidity%'
   OR c.COLUMN_NAME LIKE '%curve%'
   OR c.COLUMN_NAME LIKE '%gradient%'
   OR c.COLUMN_NAME LIKE '%track%'
   OR c.COLUMN_NAME LIKE '%route%'
   OR c.COLUMN_NAME LIKE '%load%'
   OR c.COLUMN_NAME LIKE '%brake%'
   OR c.COLUMN_NAME LIKE '%slip%'
   OR c.COLUMN_NAME LIKE '%slide%'
   OR c.COLUMN_NAME LIKE '%bearing%'
   OR c.COLUMN_NAME LIKE '%suspension%'
   OR c.COLUMN_NAME LIKE '%bogie%'
   OR c.COLUMN_NAME LIKE '%material%'
   OR c.COLUMN_NAME LIKE '%steel%'
ORDER BY EvidenceType, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME;
