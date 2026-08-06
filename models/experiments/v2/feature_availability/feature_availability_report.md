# Feature availability by calendar year (v2.0, gating artifact)

Read BEFORE interpreting any benchmark/importance/ablation number. A family that
appears only in recent years is a **time-marker** (its values say *when* the row
lives), not a mechanism. Fraction of intervals with non-null value per year.

| year | n | label | behavior | geometry | physics | maintenance | operational | identity_temporal | exposure_v2 | physics_v2 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | 468 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 0.000 |
| 2016 | 1,417 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 0.000 |
| 2017 | 1,268 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 0.000 |
| 2018 | 1,829 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 0.000 |
| 2019 | 3,975 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 0.000 |
| 2020 | 6,102 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.456 | 0.000 |
| 2021 | 12,041 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.467 | 0.000 |
| 2022 | 10,432 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.483 | 0.000 |
| 2023 | 15,753 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.756 | 0.282 |
| 2024 | 37,357 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.807 | 0.371 |
| 2025 | 77,505 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.809 | 0.354 |
| 2026 | 34,025 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.640 | 0.161 |

## Time-marker diagnosis (family level)

| family | earliest year with >5% coverage | coverage at that year |
| --- | ---: | ---: |
| behavior | 2015 | 1.000 |
| geometry | 2015 | 1.000 |
| physics | 2015 | 1.000 |
| maintenance | 2015 | 1.000 |
| operational | 2015 | 1.000 |
| identity_temporal | 2015 | 1.000 |
| exposure_v2 | 2015 | 0.455 |
| physics_v2 | 2023 | 0.282 |

## Time-marker diagnosis (mechanism columns, per column)

The family-level fraction above is diluted by always-present metadata columns
(coverage days, running_days, maintenance_density_per_day). These mechanism
columns are the ones whose availability shifts with the source windows:

| column | earliest year with >5% coverage | coverage at that year | last-year coverage |
| --- | ---: | ---: | ---: |
| interval_distance_km | 2023 | 0.786 | 0.246 |
| distance_per_day_km | 2023 | 0.786 | 0.246 |
| distance_since_last_inspection_km | 2023 | 0.786 | 0.246 |
| running_hours_proxy | 2025 | 0.055 | 0.898 |
| distance_since_turning_km | 2021 | 0.137 | 0.165 |
| maintenance_density_per_1000km | 2023 | 0.735 | 0.243 |
| wear_per_1000km_s1 | 2023 | 0.571 | 0.237 |
| remaining_material_per_km_s1 | 2023 | 0.164 | 0.141 |
| projected_remaining_km_s1 | 2023 | 0.230 | 0.124 |
| exposure_index_s1 | 2023 | 0.164 | 0.141 |

## Interpretation

- `interval_distance_km`, `wear_per_1000km_*`, `distance_per_day_km` are **0% before
  2023** and ~80-92% in 2023-2025: any importance/ablation on them is entangled with
  the RTIS-window boundary. In the grouped temporal split, train rows (2014-2021) are
  almost all missing them, so the model can only exploit them on recent rows.
- `running_hours_proxy` is a **pure time-marker** (0% until 2025, 90% in 2026): treat
  any signal it carries as suspect until a non-window-confounded source exists.
- `physics_v2` (WS3) rides entirely on the same RTIS window -> same caveat.
- Mitigation used in WS4/WS5: report availability-normalized arms and call out
  time-confounded families explicitly instead of claiming mechanistic value.
