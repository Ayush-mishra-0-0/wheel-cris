# Distance validation vs timetable ground-truth

Pairs evaluated: 864,675 (consecutive stations with positive timetable km across 2,858 trains).
Both stations snapped to the SAME rail edge: 195,800 (22.6%).

## Rail-matched distance vs timetable km

- median |% error|: 1.79%
- mean |% error|: 5.42%
- median |km error|: 0.49 km
- pairs within 10%: 88.1%
- pairs within 25%: 95.5%
- Spearman(rail_km, timetable_km): 0.989

## Geodesic distance vs timetable km (reference — should be a lower bound)

- median |% error|: 5.81%
- median % bias: -5.56%
- Spearman(geo_km, timetable_km): 0.991

## Worst 10 rail-matched errors (station_a -> station_b, rail vs timetable)

| station_a | station_b | rail_km | timetable_km | err_km | err_pct |
| --- | --- | ---: | ---: | ---: | ---: |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |
| NBQ | GLPT | 34.4 | 122.0 | -87.6 | -71.8% |

## Interpretation

- rail_km improves on geodesic where the network is aligned to real routes;
  the simplified open network has coarse vertices, so absolute rail_km is an
  ESTIMATE (EXPERIMENTAL_NOT_RELEASED), not authoritative chainage.
- pairs that do not snap to the same edge (different lines, yards, halts) fall
  back to geo_km and are flagged (same_edge=False) rather than invented.
- Validation uses timetable cumulative km as an independent cross-check only.
