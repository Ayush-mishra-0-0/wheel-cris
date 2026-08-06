# Phase 2 — Feature Engineering, Gold Datasets & Modeling: Architecture

Status: **IN PROGRESS (2026-08-06)** · Principal ML Systems & Architecture Advisor context.

## Scope decision (this sprint)

- **WS1 (Exposure), WS2 (Gold v2), WS3 (Physics)** — BUILD, by *extending* the released
  v1.2 chain (no parallel rebuild).
- **ML execution WS1-5 (benchmark / interpretability / error analysis / family
  attribution / ablation)** — DONE on Gold Dataset v2.0 (results below).
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
| WS1-5 (ML) | Benchmark, interpretability, error analysis, family attribution, ablation on v2.0 | DONE (2026-08-06, results below) | Modeling |
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

1. ~~Phase 2.4 benchmarking rig~~ **DONE** — see WS1-5 results section above.
2. Feature-store registration of approved WS1 columns (READY_FOR_MATERIALISATION set).
3. Weather provider acquisition to close WS1 weather.
4. WS4/WS5 when sources arrive.
5. Engineering wear sign-off for `wear_per_1000km_*` release decision (availability-gated).

## WS1-5 ML results on Gold v2.0 (2026-08-06)

Scripts in `models/phase2/`; outputs in `models/experiments/v2/`. Missingness: native-NaN
for trees; family-median impute + one indicator per family for Linear/RF.

### WS1 benchmark (`benchmark_summary.md`; `run_benchmark.py`)

| model | grouped RMSE (test) | rolling RMSE (median) |
| --- | ---: | ---: |
| random_forest | 14.537±0.005 | 28.932 |
| linear | 14.968 | 29.121 |
| catboost | 14.475±0.017 | 29.388 |
| hist_gradient_boosting | 14.498±0.023 | 29.620 |
| xgboost | 14.516±0.007 | 29.620 |
| lightgbm | 14.533±0.010 | 29.686 |
| dummy_mean | 23.604 | 36.234 |

- Rolling ≈ 2× grouped (deployed-prediction realism; matches v1.2/v1.3).
- All real models beat dummy by ~18% in both protocols. No single model dominates;
  tree ensembles within ~1% of each other.
- **LightGBM = interpretability workhorse**: within 0.24% of HGB grouped, 0.22% rolling
  (owner gate ≤1-2% PASSED) → used for WS2/WS4.

### WS2 interpretability (`interpretability/experiment_0001`; `interpretability.py`)

- TreeSHAP test-split: `phys_remaining_material_mm_s1` dominates (|mean SHAP| 11.0),
  then `geom_wsmTireThikness1` (4.5), `geom_wsmDia1` (2.2).
- Family share of |SHAP|: physics 46%, geometry 27%, exposure_v2 9%, operational 9%,
  maintenance 5%, rest <2%.
- PDPs physically consistent: less remaining material / thinner tire → more predicted wear.
- `running_hours_proxy` SHAP partly encodes "when in history" (time-marker confound).

### WS3 error analysis (`error_analysis/`; `error_analysis.py`)

- **Under-prediction dominates error**: negative-residual RMSE 17.7 vs positive 11.8 —
  the model misses large wear events (asymmetric, safety-relevant).
- Turning intervals slightly harder (RMSE 16.1 vs 14.5 non-turning, n=307) — weak signal.
- Yearly confound visible: RMSE 18.6 (2024) / 16.8 (2025) vs 12.5 (2026); higher where
  exposure_v2 present (15.5) than absent (14.3).

### WS4 family attribution (`family_attribution/`; `family_attribution.py`)

- SHAP: physics 46%, geometry 27% of total |SHAP|; physics dominant-row 90%.
- Leave-one-in: geometry alone RMSE 14.9, physics alone 15.4 — nearly the full 14.47;
  behavior/maintenance/operational alone near-dummy (22-24).
- Drop-family displacement: operational (1.89), maintenance (1.87), exposure_v2 (1.62)
  move predictions most; physics_v2 least (1.22).

### WS5 ablation (`ablation/`; `ablation.py`)

- LOO (RMSE rise when family removed): maintenance +0.23, operational +0.10,
  exposure_v2 +0.045; physics_v2 and behavior ≈ 0 / slightly negative.
- Forward (LightGBM): geometry → exposure_v2 → maintenance → operational reaches
  14.42 (better than full 14.47); physics_v2/physics overfit if added late.
- Availability-normalized (LOO delta on present-rows only): exposure_v2 +0.073 (vs
  +0.045 diluted), confirming its post-2023-only contribution; physics_v2 still ≈0.

### Cross-cutting finding

Geometry + physics (v1.2 features) carry ~all signal; exposure_v2 adds a small real
increment where available (post-2023), physics_v2 adds ~nothing yet. Under-prediction of
large wear is the dominant error mode for intervention planning.
