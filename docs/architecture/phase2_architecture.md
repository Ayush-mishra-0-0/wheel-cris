# Phase 2 — Feature Engineering, Gold Datasets & Modeling: Architecture

Status: **IN PROGRESS (2026-08-05)** · Principal ML Systems & Architecture Advisor context.

## Scope decision (this sprint)

- **WS1 (Exposure), WS2 (Gold v2), WS3 (Physics)** — BUILD, by *extending* the released
  v1.2 chain (no parallel rebuild).
- **WS4 (Telemetry), WS5 (Track geometry)** — DEFERRED; only design sketches below, no build.
- Distance subsystem: frozen (no further micro-optimisation). The RTIS safe daily
  aggregation is **owner-APPROVED (2026-08-05)**: `interval_distance_km` may be materialised.

## Grounding (what already exists)

- Bronze→Silver→Gold→Feature Store v1.0→model datasets v1.0–v1.2, released & validated.
- v1.2 dataset: 202,172 supervised intervals, 96 X features (wheel geometry `geom_*`,
  physics `phys_*`, maintenance, operational, identity), 6 labels, grouped temporal
  70/15/15 split. Champion: HistGradientBoosting, RMSE 14.566, R² 0.530, Spearman 0.646.
- Distance chain (Phase 1, `distance_recovery/`): approved safe daily ledger
  `rtis_daily_safe.parquet` (1,325,675 loco-days), FOIS map-matched transitions
  (15.5M rows), RTIS/FOIS adjudication (80 double-counts corrected).
- Feature governance: `configs/engineering_feature_specification_v1.json` (status
  vocabulary READY / READY_WITH_CAVEAT / READY_FOR_MATERIALISATION / PENDING / BLOCKED /
  FUTURE; blocked-value rule).

## Workstream map

| WS | Deliverable | Status | Owner layer(s) |
| --- | --- | --- | --- |
| WS1 | Exposure layer: distance_since_last_inspection, distance_per_day, running days/hours, weather, maintenance_density | DONE (v2.0, weather PENDING) | Exposure |
| WS2 | Gold Dataset v2: Wheel + Maintenance + Operational + Physics + Target | DONE (v2.0, extends v1.2) | Dataset |
| WS3 | Physics-informed: wear_per_1000km, distance_since_turning, remaining_material_per_km, exposure_index | DONE (v2.0, experimental) | Degradation/Physics |
| WS4 | Telemetry architecture (bronze/silver/gold + feature store) | DEFERRED (design only) | Platform |
| WS5 | Track geometry (schema, joins, identifiers, versioning) | DEFERRED (design only) | Route |

## WS1 — Exposure layer (built)

Builder `model_datasets/build_exposure_features_v2.py` → `model_datasets/v2/exposure_features_v2.parquet`
keyed by `operational_exposure_id` (202,172 rows).

- `interval_distance_km` — owner-approved sum of `rtis_km_safe` over (start, end], day
  granularity. Coverage 62.7% (RTIS window 2023-02-06 → 2025-12-31).
- `distance_per_day_km` = interval_distance_km / interval_days.
- `distance_since_last_inspection_km` — approved interval travel (boundary IS since the
  last wheel inspection).
- `running_days` / `running_days_pct` — interval days with approved distance > 0.
- `running_hours_proxy` — FOIS active movement time (bounded gaps ≤ 6h). Coverage 17%.
- `maintenance_density_per_day` / `per_1000km` — job cards per day / per 1000 km.
- `distance_since_turning_km` — cumulative approved km since last wsmturning=1 (per
  wheelset equipment). Coverage 18%.
- `weather_exposure_index` — **NOT materialised** (no provider; stays PENDING, blocked-value rule).

Point-in-time safe: daily reports with day ≤ interval_end only. Boundary (start, end].

## WS3 — Physics-informed (built)

Derived in `model_datasets/build_model_dataset_v2.py` from v1.2 columns + WS1 distance.

- `wear_per_1000km_s1/s2` — clean-interval (no turning at end) material loss per 1000 km,
  floor ≥ 50 km attributable distance. Coverage 53%.
- `remaining_material_per_km_s1/s2` = phys_remaining_material_mm / distance_since_turning_km.
- `projected_remaining_km_s1/s2` = remaining material / wear-per-km (lifetime estimate).
- `exposure_index_s1/s2` = (distance_since_turning_km/1000) × phys_wear_fraction.

Wear-derived features are **EXPERIMENTAL**: they depend on the engineering wear definition
(docs/degradation_semantics.md) and stay out of the released Feature Store until sign-off.

## WS2 — Gold Dataset v2 (built)

`model_datasets/build_model_dataset_v2.py` → `model_datasets/v2/model_dataset_v2.0.parquet`
+ split files + manifest + dataset card + **DATA_ADDITIONS.json** + **CHANGELOG.md**.

- v1.2 96-feature X block byte-identical; splits and labels unchanged (202,172 rows,
  train 144,373 / val 29,734 / test 28,065).
- Appends 19 columns: 11 WS1 exposure + 8 WS3 physics (s1/s2).
- Reconstruction: rerun the two builders in order (commands in DATA_ADDITIONS.json).

## Governance status changes (2026-08-05)

- `interval_distance_km`: BLOCKED → **READY_FOR_MATERIALISATION** (owner sign-off).
- `interval_distance_km_experimental`: UNCHANGED (un-renamed, constraint honoured).
- `weather_exposure_index`: PENDING (unchanged).
- Wear-derived columns: EXPERIMENTAL (pending engineering sign-off), recorded per-column.

## WS4 — Telemetry architecture (DEFERRED — design sketch)

To be built only when a telemetry feed arrives (no GPS/vibration/brake telemetry today;
`INTEG_FOIS_LocoLocation` is empty).

```text
bronze/  raw feed per source, immutable, sha256 + source_ingested_at_utc
silver/  normalised, deduped, point-in-time valid, business keys (loco_id, wsm_equipment_id, ts)
gold/    entity fact tables + feature rows (feature store source of truth)
feature_store/  feature_registry.json (status/owner/formula/lineage), feature_quality.json,
                feature_store_vN.parquet, lineage.json
```

Key rules (align with existing `feature_store/feature_store_contract.md` and
`docs/continuous_evolution_guide.md`): immutable bronze; versioned silver/gold (never
overwrite, `--force`); every materialised feature registers in the spec with grain,
availability_time, point_in_time_safe, expected_missing_pct; blocked/pending features are
never materialised as estimates.

## WS5 — Track geometry (DEFERRED — design sketch)

Principal external-data gap: no authoritative chainage/curvature source acquired
(IR Geoportal is the candidate; `docs/ir_geoportal_acquisition_plan.md`).

Schema sketch (future):
```text
track_edges (edge_id, zone, division, section, from_chainage, to_chainage, km)
track_curvature (edge_id, chainage_from, chainage_to, radius_m, gradient)
track_version (geometry_version, effective_from, effective_to, source, sha256)
station_chainage (station_code, edge_id, chainage_km)   # join key: station_code
loco_route_segment (loco_id, edge_id, chainage_from, chainage_to, ts_from, ts_to)
```
Identifiers: station_code (canonicalised FOIS code), edge_id (stable geometry identity),
versioned geometry so route segments resolve against the geometry valid at report time.
Joins: FOIS station/time sequence → station_chainage → track_edges (map-matching, cf.
`distance_recovery/` matcher) → curvature/gradient exposure per interval.

## Next actions after this sprint

1. Phase 2.4 benchmarking rig (RF/HGB/XGB/CatBoost/LightGBM/Linear + SHAP/permutation/
   residuals) on v2.0 — see `models/` experiment harness (`evaluate.py`,
   `experiment_registry.py`).
2. Feature-store registration of approved WS1 columns (READY_FOR_MATERIALISATION set).
3. Weather provider acquisition to close WS1 weather.
4. WS4/WS5 when sources arrive.
