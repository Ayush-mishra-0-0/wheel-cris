-- Cross-validation extract: paired RTIS + FOIS location reports for one loco.
--
-- FOIS_LocoLocation_History carries the RTIS event AND the FOIS report in the
-- SAME row, so division-sequence agreement can be tested directly:
--   RTIS division sequence  (RTISEvnttime, RTISDvsn)
--   FOIS division sequence  (FOISrptgtime, FOISDvsn)
-- Station-level agreement uses RTISSttn vs FOISSttn; geographic plausibility
-- uses RTISLatd/RTISLngt (scaled int) vs the FOIS station's coordinates.
--
-- Run and save as distance_recovery/data/rtis_fois_paired.parquet (the input
-- contract for 05_validate_rtis_vs_fois.py --paired).
SELECT
    LocoNumb        AS loco,
    RTISEvnttime    AS rtis_time,
    RTISZone        AS rtis_zone,
    RTISDvsn        AS rtis_division,
    RTISSttn        AS rtis_station,
    RTISLatd        AS rtis_lat_scaled,
    RTISLngt        AS rtis_lon_scaled,
    FOISrptgtime    AS fois_time,
    FOISZone        AS fois_zone,
    FOISDvsn        AS fois_division,
    FOISSttn        AS fois_station
FROM FOIS_LocoLocation_History
WHERE LocoNumb IS NOT NULL
  AND RTISEvnttime IS NOT NULL
  AND FOISrptgtime IS NOT NULL
  AND (RTISSttn IS NOT NULL OR RTISLatd IS NOT NULL)
ORDER BY LocoNumb, RTISEvnttime;
