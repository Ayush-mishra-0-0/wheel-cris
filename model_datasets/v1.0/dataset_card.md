# Dataset Card — model dataset v1.0

- **Rows (supervised):** 202,237
- **Features (X):** 58 (NA cells in X: 0)
- **Labels:** 6 (next_interval_dia_delta_mm, next_interval_root_delta_mm, next_interval_turning_flag, next_interval_large_loss_flag, time_to_next_turning_days, censored_flag)
- **Wheelsets:** 15,409
- **Locomotives:** 2,072
- **Date range:** 2015-01-18 → 2026-07-22
- **Split rows:** train=144,428 · val=29,743 · test=28,066
- **Grouped split:** by median interval-end per wheelset (no wheelset spans splits)

## Provenance

- `feature_store_version`: 1.0.0
- `feature_spec_version`: 1.0.0
- `label_spec_version`: 1.0.0
- `fingerprint`: `c01d6e55e800e0b5`
- Generated: 2026-08-03T07:56:42.267328+00:00

## Missingness summary (X features)

| Column | NA rows | NA % |
| --- | ---: | ---: |
| interval_days | 0 | 0.00% |
| diameter_delta_raw_mm_side_1 | 0 | 0.00% |
| diameter_delta_raw_mm_side_2 | 0 | 0.00% |
| rtis_source_event_count | 0 | 0.00% |
| rtis_source_event_type_count | 0 | 0.00% |
| maintenance_jobcard_creation_count | 0 | 0.00% |
| rtis_reporting_coverage_pct | 0 | 0.00% |
| rtis_report_count | 0 | 0.00% |
| rtis_reporting_days | 0 | 0.00% |
| rtis_duplicate_report_count | 0 | 0.00% |
| wheel_position_1_12 | 0 | 0.00% |
| axle_position_1_6 | 0 | 0.00% |
| inspection_count_through_interval_end | 0 | 0.00% |
| wheel_profile_2class | 0 | 0.00% |
| wheel_schedule_id__1.0 | 0 | 0.00% |
| wheel_schedule_id__10.0 | 0 | 0.00% |
| wheel_schedule_id__12.0 | 0 | 0.00% |
| wheel_schedule_id__13.0 | 0 | 0.00% |
| wheel_schedule_id__14.0 | 0 | 0.00% |
| wheel_schedule_id__18.0 | 0 | 0.00% |
| wheel_schedule_id__19.0 | 0 | 0.00% |
| wheel_schedule_id__20.0 | 0 | 0.00% |
| wheel_schedule_id__3.0 | 0 | 0.00% |
| wheel_schedule_id__32.0 | 0 | 0.00% |
| wheel_schedule_id__34.0 | 0 | 0.00% |
| wheel_schedule_id__38.0 | 0 | 0.00% |
| wheel_schedule_id__39.0 | 0 | 0.00% |
| wheel_schedule_id__4.0 | 0 | 0.00% |
| wheel_schedule_id__41.0 | 0 | 0.00% |
| wheel_schedule_id__5.0 | 0 | 0.00% |
| wheel_schedule_id__6.0 | 0 | 0.00% |
| wheel_schedule_id__7.0 | 0 | 0.00% |
| wheel_schedule_id__77.0 | 0 | 0.00% |
| wheel_schedule_id__8.0 | 0 | 0.00% |
| home_shed__freq | 0 | 0.00% |
| defect_zone__-1.0 | 0 | 0.00% |
| defect_zone__1.0 | 0 | 0.00% |
| defect_zone__10.0 | 0 | 0.00% |
| defect_zone__11.0 | 0 | 0.00% |
| defect_zone__12.0 | 0 | 0.00% |
| defect_zone__13.0 | 0 | 0.00% |
| defect_zone__14.0 | 0 | 0.00% |
| defect_zone__15.0 | 0 | 0.00% |
| defect_zone__16.0 | 0 | 0.00% |
| defect_zone__18.0 | 0 | 0.00% |
| defect_zone__2.0 | 0 | 0.00% |
| defect_zone__20.0 | 0 | 0.00% |
| defect_zone__3.0 | 0 | 0.00% |
| defect_zone__4.0 | 0 | 0.00% |
| defect_zone__5.0 | 0 | 0.00% |
| defect_zone__6.0 | 0 | 0.00% |
| defect_zone__7.0 | 0 | 0.00% |
| defect_zone__8.0 | 0 | 0.00% |
| defect_zone__9.0 | 0 | 0.00% |
| defect_division__freq | 0 | 0.00% |
| wheel_age_days_proxy | 0 | 0.00% |
| turning_indicator_raw | 0 | 0.00% |
| days_since_turning | 0 | 0.00% |

## Label prevalence

| Label | prevalence / mean |
| --- | --- |
| next_interval_dia_delta_mm | 0.5856 |
| next_interval_root_delta_mm | 0.1074 |
| next_interval_turning_flag | 0.0113 |
| next_interval_large_loss_flag | 0.6160 |
| time_to_next_turning_days | 192.0452 |
| censored_flag | 0.9135 |

## Known limitations

1. Labels are candidate (not approved): see `configs/label_specification.json` `validation_status`.
2. `next_interval_turning_flag` is imbalanced (~1.8% positive); flag may undercount ~0.6% of pairs (Q2).
3. `time_to_next_turning_days` is 90% right-censored; evaluate with survival metrics (C-index), not plain RMSE.
4. `next_interval_large_loss_flag` uses heuristic thresholds (-2.0 mm dia / -1.0 mm root).
5. Encoders and imputers were fit on TRAIN only; NA sentinels: ordinal_binary=-1, one_hot/frequency="__NA__" bucket.
6. `next_interval_dia_delta_mm` / `next_interval_root_delta_mm` contain raw sentinel outliers (min/max ~±1090 mm / ±2047 mm) from source measurements outside quarantine [600,1300] mm dia; regression RMSE will be inflated until a quarantined label version (label_spec >= 1.1).
