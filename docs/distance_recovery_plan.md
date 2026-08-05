# Physical-distance recovery plan

## Current decision

No physical-distance feature is released. `distance_km` remains null with
`BLOCKED_PENDING_SOURCE_CONFIRMATION` in Operational Exposure v1.0.

## Alternative-source assessment (2026-07-29)

| Rank | Option | What SQL Server evidence shows | What may be used now | Distance decision |
| --- | --- | --- | --- | --- |
| 1 | `view_locolocation_trackhistory` FOIS history | 15,577,312 WAP7 records for 2,272 locomotives (2025-10-27 to 2026-06-10); station and location time are populated on virtually every record; only 27 duplicate locomotive/time/station keys. | Ordered station/time, zone/division and limited train context for operational/route coverage. | Best route-reconstruction candidate, but no route length, chainage, or coordinates are present. Requires an authoritative station/track-segment/chainage network before calculating km. |
| 2 | `MovementRegister` | 453,287 WAP7 rows; 144,754 are `Under Maintenance`, 307,394 have null status, and only 274 are `In Use`. Meter/mileage values also have implausible outliers and continuity failures. | Maintenance/shed context only, subject to its own semantics. | Rejected as a fleet operational-distance ledger. Do not sum or difference its raw meter fields. |
| 3 | `INTEG_FOIS_LocoLocation` GPS | Schema has event time and integer latitude/longitude fields, but the current table contains zero rows. | None. | Cannot calculate anything until the source is populated and coordinate scale/quality are verified. |
| 4 | Section/block traversal catalogue search | No locomotive-time section/block/chainage traversal ledger was identified; candidates were maintenance/asset section tables. | None. | Blocked pending a real traffic-control, GIS, or infrastructure traversal feed. |
| 5 | `RtisLocoKmDetails` | Multiple division reports and duplicates; tested aggregations yield physically implausible daily totals. | **APPROVED (2026-08-05)** daily ledger: dedupe + per-loco-day SUM with combined outlier rejection → `rtis_daily_safe.parquet` (1,325,675 loco-days). | **Resolved by owner sign-off** of the aggregation rule (grain = loco-day, dedupe on business key, multi-division sum, outliers adjudicated by FOIS). |

## GPS distance rule if a populated coordinate feed arrives

Latitude/longitude pairs may support a **geodesic lower-bound estimate** after
deduplication, valid-coordinate checks, timestamp ordering, speed/time-gap
plausibility and gap coverage checks. Haversine distance between points is not
rail distance: it cuts across curves, junctions and parallel tracks. A released
rail kilometre value needs map matching to an authoritative rail network or
route/chainage segments, direction/route validation, and a documented treatment
of gaps. Until then call the result `gps_geodesic_distance_km_estimate`, never
`distance_km`.

## Shortest path to released rail kilometres

1. Obtain the RTIS owner-approved physical-distance rule; this remains the
   fastest possible direct mileage route.
2. Acquire authoritative station-to-track/chainage or GIS route-network data
   for the FOIS track-history station sequence.
3. If GPS becomes populated, map-match the points to the approved network and
   retain coverage/confidence rather than treating straight-line distance as
   actual rail travel.
