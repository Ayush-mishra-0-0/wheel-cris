# Dataset Card — model dataset v2.0

- **Parent:** v1.2 (immutable; 96-feature X block + split + labels identical for retained rows)
- **Rows (supervised):** 202,172
- **Added columns:** 19 (WS1 exposure + WS3 physics)
- **Label spec:** 1.0.1 (unchanged from v1.2)
- **Split rows:** train=144,373 · val=29,734 · test=28,065
- Generated: 2026-08-05T06:22:12.238452+00:00

## Phase-2 additions

| column | expected missing % |
| --- | ---: |
| remaining_material_per_km_s1 | 86.1 |
| exposure_index_s1 | 86.1 |
| remaining_material_per_km_s2 | 86.1 |
| exposure_index_s2 | 86.1 |
| running_hours_proxy | 82.8 |
| distance_since_turning_km | 81.9 |
| projected_remaining_km_s1 | 79.5 |
| projected_remaining_km_s2 | 79.5 |
| wear_per_1000km_s1 | 47.0 |
| wear_per_1000km_s2 | 47.0 |
| maintenance_density_per_1000km | 39.6 |
| interval_distance_km | 37.3 |
| distance_per_day_km | 37.3 |
| distance_since_last_inspection_km | 37.3 |
| rtis_distance_coverage_days_in_interval | 0.0 |
| rtis_distance_coverage_pct_in_interval | 0.0 |
| running_days | 0.0 |
| running_days_pct | 0.0 |
| maintenance_density_per_day | 0.0 |

## Governance

- Distance features use the owner-APPROVED safe daily aggregation (2026-08-05).
- `interval_distance_km_experimental` remains un-renamed/untouched.
- Wear-derived columns are EXPERIMENTAL (engineering wear definition not yet signed off).
- `weather_exposure_index` is NOT materialised (PENDING, no provider).
