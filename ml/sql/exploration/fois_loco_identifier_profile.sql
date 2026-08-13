-- Identifier type, length and character-pattern distribution for reconciliation.
WITH identifiers AS (
    SELECT 'FOIS_LocoLocation_History.LocoNumb' AS source_name, LocoNumb AS identifier
    FROM FOIS_LocoLocation_History
    WHERE NULLIF(LTRIM(RTRIM(LocoNumb)), '') IS NOT NULL
    UNION ALL
    SELECT 'LocoMaster.LomNumber', LomNumber
    FROM LocoMaster
    WHERE NULLIF(LTRIM(RTRIM(LomNumber)), '') IS NOT NULL
), distinct_identifiers AS (
    SELECT DISTINCT source_name, identifier FROM identifiers
), classified AS (
    SELECT
        source_name,
        identifier,
        LEN(identifier) AS identifier_length,
        CASE WHEN identifier LIKE ' %' OR identifier LIKE '% ' THEN 1 ELSE 0 END AS has_outer_whitespace,
        CASE WHEN LTRIM(RTRIM(identifier)) LIKE '0%' THEN 1 ELSE 0 END AS has_leading_zero,
        CASE
            WHEN LTRIM(RTRIM(identifier)) NOT LIKE '%[^0-9]%' THEN 'digits_only'
            WHEN REPLACE(LTRIM(RTRIM(identifier)), ' ', '') NOT LIKE '%[^0-9]%' THEN 'digits_with_spaces'
            WHEN LTRIM(RTRIM(identifier)) LIKE '%[A-Za-z]%' THEN 'alphanumeric'
            ELSE 'other'
        END AS character_pattern
    FROM distinct_identifiers
)
SELECT
    source_name,
    identifier_length,
    has_outer_whitespace,
    has_leading_zero,
    character_pattern,
    COUNT(*) AS distinct_identifier_count
FROM classified
GROUP BY source_name, identifier_length, has_outer_whitespace, has_leading_zero, character_pattern
ORDER BY source_name, identifier_length, has_outer_whitespace, has_leading_zero, character_pattern;
