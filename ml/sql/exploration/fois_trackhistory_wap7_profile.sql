-- Assess the 88M-row FOIS track-history source as a route/event ledger.
WITH wap AS (
    SELECT h.HistoryID, h.LocoNumber, h.Station, h.LastLocationTime, h.TrainNo,
        h.ZonCode, h.DivCode, h.RecordCreatedTimestamp
    FROM view_locolocation_trackhistory AS h
    INNER JOIN LocoMaster AS l ON h.LocoNumber = l.LomNumber
    INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
    WHERE lt.LotTypeName = '{{COHORT}}'
), duplicate_keys AS (
    SELECT LocoNumber, LastLocationTime, Station, COUNT_BIG(*) AS occurrences
    FROM wap GROUP BY LocoNumber, LastLocationTime, Station HAVING COUNT_BIG(*) > 1
)
SELECT metric, value FROM (
    SELECT 'wap7_rows' AS metric, CAST(COUNT_BIG(*) AS decimal(19,2)) AS value FROM wap
    UNION ALL SELECT 'wap7_distinct_locos', CAST(COUNT(DISTINCT LocoNumber) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'rows_with_location_time', CAST(COUNT(LastLocationTime) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'rows_with_station', CAST(COUNT(CASE WHEN Station IS NOT NULL AND Station <> '' THEN 1 END) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'rows_with_train_number', CAST(COUNT(CASE WHEN TrainNo IS NOT NULL AND TrainNo <> '' THEN 1 END) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'min_location_time_as_yyyymmdd', CAST(CONVERT(char(8), MIN(LastLocationTime), 112) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'max_location_time_as_yyyymmdd', CAST(CONVERT(char(8), MAX(LastLocationTime), 112) AS decimal(19,2)) FROM wap
    UNION ALL SELECT 'duplicate_loco_time_station_keys', CAST(COUNT_BIG(*) AS decimal(19,2)) FROM duplicate_keys
) AS metrics ORDER BY metric;
