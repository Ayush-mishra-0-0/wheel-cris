-- Full distinct-set match rates. Each strategy is independently normalised on
-- both systems; rate denominator is all nonblank distinct FOIS identifiers.
WITH f AS (
    SELECT DISTINCT LocoNumb AS raw_value
    FROM FOIS_LocoLocation_History
    WHERE NULLIF(LTRIM(RTRIM(LocoNumb)), '') IS NOT NULL
), l AS (
    SELECT DISTINCT LomNumber AS raw_value
    FROM LocoMaster
    WHERE NULLIF(LTRIM(RTRIM(LomNumber)), '') IS NOT NULL
), normalised AS (
    SELECT 'raw_exact' AS strategy, raw_value AS fois_value, raw_value AS normalised_value FROM f
    UNION ALL SELECT 'trim', raw_value, LTRIM(RTRIM(raw_value)) FROM f
    UNION ALL SELECT 'uppercase_trim', raw_value, UPPER(LTRIM(RTRIM(raw_value))) FROM f
    UNION ALL SELECT 'remove_all_spaces', raw_value, REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '') FROM f
    UNION ALL SELECT 'remove_leading_zeros', raw_value,
        CASE WHEN REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '') NOT LIKE '%[^0]%' THEN '0'
             ELSE SUBSTRING(REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', ''), PATINDEX('%[^0]%', REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '')), 8000) END
    FROM f
), normalised_master AS (
    SELECT 'raw_exact' AS strategy, raw_value AS normalised_value FROM l
    UNION ALL SELECT 'trim', LTRIM(RTRIM(raw_value)) FROM l
    UNION ALL SELECT 'uppercase_trim', UPPER(LTRIM(RTRIM(raw_value))) FROM l
    UNION ALL SELECT 'remove_all_spaces', REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '') FROM l
    UNION ALL SELECT 'remove_leading_zeros',
        CASE WHEN REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '') NOT LIKE '%[^0]%' THEN '0'
             ELSE SUBSTRING(REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', ''), PATINDEX('%[^0]%', REPLACE(UPPER(LTRIM(RTRIM(raw_value))), ' ', '')), 8000) END
    FROM l
), numeric_fois AS (
    SELECT DISTINCT raw_value AS fois_value, TRY_CONVERT(bigint, LTRIM(RTRIM(raw_value))) AS numeric_value FROM f
), numeric_master AS (
    SELECT DISTINCT TRY_CONVERT(bigint, LTRIM(RTRIM(raw_value))) AS numeric_value FROM l
), strategy_results AS (
    SELECT n.strategy, n.fois_value, CASE WHEN m.normalised_value IS NULL THEN 0 ELSE 1 END AS is_match
    FROM normalised AS n
    LEFT JOIN (SELECT DISTINCT strategy, normalised_value FROM normalised_master) AS m
        ON m.strategy = n.strategy AND m.normalised_value = n.normalised_value
    UNION ALL
    SELECT 'numeric_conversion', n.fois_value, CASE WHEN m.numeric_value IS NULL THEN 0 ELSE 1 END
    FROM numeric_fois AS n
    LEFT JOIN numeric_master AS m ON m.numeric_value = n.numeric_value
    WHERE n.numeric_value IS NOT NULL
)
SELECT
    strategy,
    COUNT(*) AS fois_distinct_values_evaluated,
    SUM(is_match) AS matched_fois_distinct_values,
    CAST(100.0 * SUM(is_match) / NULLIF(COUNT(*), 0) AS decimal(6,2)) AS match_rate_percent
FROM strategy_results
GROUP BY strategy
ORDER BY CASE strategy
    WHEN 'raw_exact' THEN 1 WHEN 'trim' THEN 2 WHEN 'uppercase_trim' THEN 3
    WHEN 'remove_all_spaces' THEN 4 WHEN 'remove_leading_zeros' THEN 5
    WHEN 'numeric_conversion' THEN 6 END;
