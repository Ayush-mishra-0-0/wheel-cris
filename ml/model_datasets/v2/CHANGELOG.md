# Model dataset change log (Phase 2)

## v2.0 — 2026-08-05

### Workstream 1 — Operational Exposure (added)
- `interval_distance_km`, `distance_per_day_km`, `distance_since_last_inspection_km`, `running_days`, `running_days_pct` — from the **owner-APPROVED** RTIS safe daily ledger (07_safe_rtis_daily_aggregation.py, signed off 2026-08-05).
- `rtis_distance_coverage_days/pct_in_interval` — reporting-day coverage of the sum.
- `running_hours_proxy` — FOIS active-movement time (bounded gaps); low coverage (FOIS window 2025-10 -> 2026-06).
- `maintenance_density_per_day` / `maintenance_density_per_1000km` — job cards per day / per 1000 km.
- `distance_since_turning_km` — cumulative approved km since last wsmturning=1 (per wheelset equipment; NULL if none in history).

### Workstream 3 — Physics-informed (added)
- `wear_per_1000km_s1/s2` — clean-interval material loss per 1000 km (no turning at interval end). EXPERIMENTAL: engineering wear definition pending sign-off.
- `remaining_material_per_km_s1/s2` — remaining material per km run since turning.
- `projected_remaining_km_s1/s2` — remaining material / wear-per-km lifetime estimate.
- `exposure_index_s1/s2` — distance-since-turning (1000 km) x material-consumed fraction.

### Not materialised
- `weather_exposure_index` — PENDING (no provider).
- Track curve severity — FUTURE (WS5 deferred).

### Governance notes
- `interval_distance_km_experimental` left un-renamed/untouched.
- v1.2 96-feature X block byte-identical; splits and labels unchanged.

### Reconstruction
```powershell
.ayush\Scripts\python.exe model_datasets\build_exposure_features_v2.py --force
.ayush\Scripts\python.exe model_datasets\build_model_dataset_v2.py --force
```
