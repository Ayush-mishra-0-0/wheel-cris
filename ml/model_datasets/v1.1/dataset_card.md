# Dataset Card — model dataset v1.1

- **Parent:** v1.0 (immutable; rows/splits/labels identical)
- **Rows (supervised):** 202,237
- **Features (X):** 96 (v1.0: 58 + augmentation: 38)
- **Physics join match:** 201,221 rows (99.50%)

## Augmentation feature groups (point-in-time safe, as-of interval end)

| Group | Columns |
| --- | --- |
| Raw measured geometry at interval end (geom_*) | geom_wsmDia1, geom_wsmDia2, geom_wsmRoot1, geom_wsmRoot2, geom_wsmFlange1, geom_wsmFlange2, geom_wsmFlangeThickness1, geom_wsmFlangeThickness2, geom_wsmWear, geom_wsmWear2, geom_wsmWearRate, geom_wsmWearRate2, geom_wsmTireThikness1, geom_wsmTireThikness2, geom_wsmThread1, geom_wsmThread2, geom_wsmKvalue1, geom_wsmSDistance1 |
| Level 1 material state | phys_initial_dia_mm_s1, phys_remaining_material_mm_s1, phys_wear_fraction_s1, phys_material_consumed_pct_s1, phys_initial_dia_mm_s2, phys_remaining_material_mm_s2, phys_wear_fraction_s2, phys_material_consumed_pct_s2 |
| Level 2 wear trends | phys_cumulative_wear_mm_s1, phys_interval_wear_rate_s1, phys_wear_acceleration_s1, phys_ema_wear_rate_s1, phys_remaining_budget_days_s1, phys_cumulative_wear_mm_s2, phys_interval_wear_rate_s2, phys_wear_acceleration_s2, phys_ema_wear_rate_s2, phys_remaining_budget_days_s2 |
| Life-cycle state | phys_turning_events_cumulative, phys_wheelset_age_days |

- Physics constants: condemning dia = 1016.0 mm, new dia = 1096.0 mm (domain-provided).
- geom_* columns are the absolute measured wheel geometry at interval_end (the prediction timestamp) — previously excluded from v1.0, which carried only interval deltas.
- NA imputed with TRAIN median (same policy as v1.0 numeric features).
