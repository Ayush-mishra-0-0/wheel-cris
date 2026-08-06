# WS2 Interpretability — LightGBM TreeSHAP (v2.0)

Test RMSE 14.524 (matches WS1). SHAP via TreeExplainer on raw native-NaN X.

## Family attribution (sum |mean SHAP|)

| family | sum \|mean SHAP\| |
| --- | ---: |
| physics | 14.6458 |
| geometry | 8.5846 |
| exposure_v2 | 2.9872 |
| operational | 2.9060 |
| maintenance | 1.6173 |
| identity_temporal | 0.6496 |
| physics_v2 | 0.3090 |
| behavior | 0.0875 |

## Top-20 features (|mean SHAP|)

| feature | |mean SHAP| |
| --- | ---: |
| phys_remaining_material_mm_s1 | 11.0045 |
| geom_wsmTireThikness1 | 4.5476 |
| geom_wsmDia1 | 2.1836 |
| phys_remaining_material_mm_s2 | 1.6425 |
| defect_division__freq | 1.3181 |
| running_hours_proxy | 0.9830 |
| wheel_profile_2class | 0.8902 |
| geom_wsmTireThikness2 | 0.7602 |
| home_shed__freq | 0.6884 |
| phys_wheelset_age_days | 0.5028 |
| interval_distance_km | 0.4108 |
| wheel_age_days_proxy | 0.3626 |
| rtis_distance_coverage_pct_in_interval | 0.3494 |
| rtis_reporting_coverage_pct | 0.3344 |
| geom_wsmDia2 | 0.3183 |
| distance_per_day_km | 0.2911 |
| interval_days | 0.2735 |
| maintenance_density_per_day | 0.2283 |
| inspection_count_through_interval_end | 0.2166 |
| running_days_pct | 0.1952 |

## Caveats

- `running_hours_proxy` is a pure time-marker (0% pre-2025, 90% 2026); its SHAP
  magnitude partly encodes 'when in history', not physical exposure.
- exposure_v2 / physics_v2 are 0% present pre-2023; their SHAP is only driven by
  post-2023 rows in this grouped split.
