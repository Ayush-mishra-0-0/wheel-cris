-- Bronze/raw Sections lookup extract: decodes employee section (M4INSP etc.) into
-- section code/name. Section is the inspection/maintenance unit that took the reading.
SELECT
    SecId,
    SecCode,
    SecName,
    SecFuncLocation,
    SecType,
    SecKind,
    SecInCharge,
    SecPBSection
FROM Sections
ORDER BY SecId;