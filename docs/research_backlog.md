# Research Backlog

This is a living acquisition and research register. A backlog item must not
block the core Bronze → Silver → Engineering → Gold pipeline unless explicitly
marked as a release gate.

| Idea | Status | V1 target | Owner | Blocking? | Next evidence needed |
| --- | --- | --- | --- | --- | --- |
| Track geometry: curvature, gradient, chainage | Searching | Yes | Data/Track liaison | No | Owner, authoritative source, segment-to-RTIS mapping and effective dates |
| IR Geoportal station/track network access | Access discovery required | Yes | IR Geoportal / Track GIS owner | No | Read-only GIS service or versioned export for station reference, station-to-station/chainage edges, geometry and effective dates; see `docs/ir_geoportal_acquisition_plan.md` |
| Dynamic hauled-train load | Partial | Yes | Operations data liaison | No | Grain and coverage of wagon/rake/weight fields linked to train attachment |
| Static WAP7 axle load | Available | Yes | Engineering validation | No | Validate `LocoTypes.LotAxelLoad` unit and applicability |
| RTIS distance semantics | Pending daily-aggregation validation | Yes | RTIS data owner / engineering | Yes for distance features | Senior domain review confirms sensor-derived movement and low km during shed/stabling; next validate additive-division rule and fleet-level shed cross-check before release. See `docs/rtis_daily_distance_revalidation.md`. |
| FOIS WAP7 movement coverage | Partial: route context found | Yes | Data engineering / FOIS owner | No | `view_locolocation_trackhistory` has 15.6M WAP7 station/time records, but needs authoritative station-to-track/chainage mapping before it can yield rail km; current `INTEG_FOIS_LocoLocation` GPS table is empty |
| Historical weather API/archive | Planned | Yes | Data engineering | No | Provider, licence, spatial/temporal resolution and reproducible cache |
| Wayside WILD/OMRS wheel load and bearing alerts | Partial | Evaluate | Data engineering | No | Wider cohort coverage, parse rules and wheel/axle position semantics |
| Brake pressure | Future | No | Rolling-stock systems | No | Sensor source, sampling and locomotive/time keys |
| Wheel slip/slide | Future | No | Rolling-stock systems | No | Sensor/log source and event definitions |
| Suspension/bearing/vibration | Future | No | Rolling-stock systems | No | Sensor source, calibration and maintenance linkage |
