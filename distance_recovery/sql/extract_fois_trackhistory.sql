-- FOIS track-history extraction for distance map-matching.
--
-- Two variants:
--   A. FULL HISTORY (all loco types, whole table, ~88M rows)  -> 2016-2026 or longer
--   B. COHORT + optional date window (e.g. WAP7 regression cohort)
--
-- Run via your existing export tooling (bcp / SSIS / pyodbc) and save as
--   distance_recovery/data/fois_trackhistory_wap7.parquet
-- Columns are normalized downstream by 04_map_match_track_history.py:
--   LocoNumber -> loco, Station -> station, LastLocationTime -> location_time.
--
-- ============================================================
-- VARIANT A — WHOLE HISTORY (use this for the production run)
-- ============================================================
SELECT
    h.LocoNumber,
    h.Station,
    h.LastLocationTime,
    h.TrainNo,
    h.ZonCode,
    h.DivCode
FROM view_locolocation_trackhistory AS h
WHERE h.LastLocationTime IS NOT NULL
  AND h.Station IS NOT NULL AND h.Station <> ''
ORDER BY h.LocoNumber, h.LastLocationTime;

-- ============================================================
-- VARIANT A1 — WHOLE HISTORY, date window (e.g. 2016-01-01 .. 2026-12-31)
-- ============================================================
-- SELECT
--     h.LocoNumber,
--     h.Station,
--     h.LastLocationTime,
--     h.TrainNo,
--     h.ZonCode,
--     h.DivCode
-- FROM view_locolocation_trackhistory AS h
-- WHERE h.LastLocationTime >= '2016-01-01'
--   AND h.LastLocationTime <  '2027-01-01'
--   AND h.Station IS NOT NULL AND h.Station <> ''
-- ORDER BY h.LocoNumber, h.LastLocationTime;

-- ============================================================
-- VARIANT B — WAP7 COHORT (matches the v1.2 regression cohort)
-- ============================================================
-- SELECT
--     h.LocoNumber,
--     h.Station,
--     h.LastLocationTime,
--     h.TrainNo,
--     h.ZonCode,
--     h.DivCode
-- FROM view_locolocation_trackhistory AS h
-- INNER JOIN LocoMaster AS l ON h.LocoNumber = l.LomNumber
-- INNER JOIN LocoTypes AS lt ON lt.LotId = l.LomType
-- WHERE lt.LotTypeName = '{{COHORT}}'          -- e.g. WAP7
--   AND h.LastLocationTime IS NOT NULL
--   AND h.Station IS NOT NULL AND h.Station <> ''
-- ORDER BY h.LocoNumber, h.LastLocationTime;

-- NOTES
--   * Variant A is ~88M rows (all loco types). The WAP7 profile measured
--     15.5M rows for 2,272 WAP7 locos over ~8 months; the full table spans the
--     entire retained window, so expect many more rows over 2016-2026.
--   * Export in chunks (by LocoNumber range or LastLocationTime) if a single
--     export is too heavy; concatenate to one parquet afterwards.
--   * Do NOT filter to Station <> '' in downstream distance aggregation for
--     shed days — a missing station row is different from a shed stay. Keep all
--     rows here; filtering happens in the mapper only for distance-bearing hops.
