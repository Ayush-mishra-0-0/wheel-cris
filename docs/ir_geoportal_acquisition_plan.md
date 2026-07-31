# IR Geoportal acquisition plan

## Current finding (2026-07-29)

`https://irgeoportal.gov.in/Portal/` is an official Indian Railways
infrastructure GIS candidate. Its public page did not expose a searchable
station-distance table, downloadable network dataset, or documented public API
from this environment. Therefore no station distance, chainage, curve, gradient
or track-quality attribute is claimed as acquired.

This is an access/discovery limitation, not evidence that the data is absent.

## Request to the portal/data owner

Request either a documented read-only GIS service/API or versioned export for:

| Required dataset | Minimum attributes |
| --- | --- |
| Station reference | Stable station code, name, zone/division, latitude/longitude, line/route ID, chainage, effective date. |
| Track network / station-to-station links | Stable segment ID, from/to station or chainage, physical rail length, route/line ID, direction, gauge, effective date. |
| Track geometry | Segment/chainage, curve radius or degree, gradient, speed restriction, track class, version/effective date. |
| Track condition / maintenance | Segment/chainage, measurement date, quality index/defect, maintenance action, version. |

Also obtain the coordinate reference system, unit definitions, refresh cadence,
licence/usage approval and whether parallel lines/route alternatives are
represented.

## Integration rule

FOIS `view_locolocation_trackhistory` station/time events must first map to a
versioned station reference. Consecutive station events then map to approved
track-network edges; interval distance is the sum of those edges, with route,
direction, missing-edge and mapping-confidence fields retained. Curvature,
gradient and quality features attach to the same traversed edges.

No web-scraped station distance or straight-line coordinate distance may be
published as `distance_km`.
