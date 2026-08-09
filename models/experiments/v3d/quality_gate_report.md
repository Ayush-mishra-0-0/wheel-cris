# Phase 3D — Quality Gate Report (Gate 3D-DQ)

**Date:** 2026-08-09 · **Status:** PASS with disclosures
**Substrate:** `model_datasets/v3d/forecast_horizon_benchmark_pairs.parquet` (v1.0.0)
**Experiment root:** `models/experiments/v3d/`

This report is the blocking 3D-DQ gate per `docs/phase3d_plan.md`. It documents
the distance-coverage structure that Phase 3D inherits, the horizon-window
composition, the two-arm protocol, and the empirical (not guaranteed) conformal
coverage. All conventions of `docs/phase3c_plan.md` §10-§11 apply.

---

## 1. Distance-coverage attribution (root cause, quantified)

The gap between the 3C training coverage (~60%) and test coverage (~15%) is
**not** missing-linkage noise. Its root cause is source truncation:

| Source | Extent |
| --- | --- |
| `data/silver/rtis_mileage.parquet` (`event_timestamp`) | 2023-02-06 → **2025-12-31** |
| Frozen TEST cohort (v3c chronological 80/20) | **2025-11-24 → 2026-07-23** |

The entire test cohort overlaps the RTIS **ledger void**: coverage is ~0% for
the 2026 portion and only partially covered where the cohort straddles
2025-12-31. Coverage by measurement year (within-life rows):

| Year | rows | distance_available % |
| --- | --- | --- |
| ≤2019 | ~9k | 0.0 |
| 2020 | 7.3k | 0.0 |
| 2021 | 14.4k | 0.3 |
| 2022 | 11.4k | 7.9 |
| 2023 | 19.3k | 69.7 |
| 2024 | 46.5k | 77.3 |
| 2025 | 91.4k | 78.1 |
| 2026 | 38.4k | 0.0 |

**Disclosure:** the 2026 rows have NO RTIS distance covariate by source
truncation, not by sampled missingness. Distance is retained as native-NaN plus
a `distance_available` flag and is never imputed. Any model consuming the 2026
portion operates under "no distance" semantics. A coverage-restricted view
(`measurement_timestamp <= 2025-12-31`) is reported separately and NEVER
pooled indistinguishably with the full cohort.

**Status — PASS** (a fact under honest strata, not a blocker for forecast
delivery).

---

## 2. Horizon-window composition (v3d)

Rows: 239,684 within-lifecycle pairs; 34 state/exposure/quality features.

| Band | n (all) | n (test) | median Δt | IQR | replacement_before_H |
| --- | --- | --- | --- | --- | --- |
| 30d [20,45] | 38,060 | 9,283 | 31.0 | 25–38 | 237 |
| 60d [45,80] | 27,055 | 6,112 | 58.0 | 51–66 | 744 |
| 90d [70,120] | 43,046 | 8,346 | 94.0 | 87–99 | 1,745 |
| 180d [140,240] | 4,948 | 828 | 185 | 168–202 | 6,273 |
| 365d [300,450] | 830 | 92 | 328 | 314–385 | 16,908 |
| other | 125,745 | — | — | — | — |

- `other` rows (short sub-window / >450d gaps) are **training-only** and never
  forecast-evaluated at a nominal horizon.
- `replacement_before_{H}d` is a censoring flag from the governed Event Ledger
  (CONFIRMED+LIKELY); rows are flagged, never silently dropped.
- 365d is present but small (n_test=92): reported, never claimed as headlining.
- Band assignment is deterministic per pair (nearest nominal horizon, ties to
  smaller H).

---

## 3. Two-arm protocol (identical rows / split / seed / hyperparameters)

| Item | Arm A (time/state) | Arm B (+distance) |
| --- | --- | --- |
| features | state, quality codes, exposure, categoricals | A + interval_distance_km, distance_per_day_km, coverage_pct, distance_since_turning_km, distance_available |
| split | v3c frozen chronological cohort | identical |
| model | XGBoost (fixed, no tuning) | identical |
| seed | 42 | 42 |

Example (`wsmDia`, 90d window, MAE mm):

| view | Arm A | Arm B |
| --- | --- | --- |
| full_test | 3.546 | 3.416 |
| distance_present | 2.496 | 2.569 |
| coverage_restricted (≤2025-12-31) | 2.702 | 2.736 |

Distance does **not** consistently improve MAE (within noise); consistent with
the 3C Stage-D ablation conclusion. Full per-dimension/band/view tables live in
`forecast_benchmark_results.json`.

---

## 4. Conformal coverage — empirical temporal, not guaranteed

Split conformal, calibration = **last 10% of the chronological TRAIN rows**
(never test). Per (dimension, band, arm, 80%/95%). Example `wsmDia`:

| band | i80 empirical | i95 empirical |
| --- | --- | --- |
| 30d | 0.728 | 0.932 |
| 60d | 0.800 | 0.958 |
| 90d | 0.783 | 0.948 |
| 180d | 0.843 | 0.976 |
| 365d | 0.902 | 0.935 |

Rolling sim (74 monthly refits, 90d window): mean i80 coverage 0.778, mean i95
coverage 0.945. Coverage is reported as an **observed temporal diagnostic**, and
nominal labels (`80%`, `95%`) are only the calibration target — never a
promise. Repeatedly monitoring this under deployment is the requirement.

---

## 5. Evaluation hierarchy respected

1. **Rolling production simulation = primary** evidence
   (`rolling_forecast_sim_results.json`, 74 monthly refits, point-in-time only,
   no future facts). Note: aggregate rolling `wsmDia` 90d XGBoost mean MAE
   ≈ persistence over the early-vs-late mix; per-month is the honest frame,
   not a headline.
2. **Grouped-by-loco holdout = stress test**
   (`loco_holdout_results.json`): 3,210 of 16,050 locomotives fully held out,
   5,026 held-out test rows. Result is reported as a stress, not a promise —
   e.g. `wsmDia` XGBoost on unseen loco 30d MAE (2.44mm) vs persistence
   (1.48mm) DOES generalise less well to unseen trains; 365d is comparable.
3. Frozen chronological split is the secondary frame.

---

## 6. Guardrails honored

- No feature uses a fact newer than its score timestamp (rolling fit <= refit).
- `interval_days` is a continuous feature; the model is band-invariant, only
  *evaluated* per window (no exact-30/60/90 handle claims).
- No monolithic multi-output; per-dimension models.
- No deep sequence models in Phase 3D (per approval).
- No block/imputation of distance; distance-restricted views explicit.
- No causal claim from correlations.

---

## 7. Gate decision

| Gate | Requirement | Status |
| --- | --- | --- |
| 3D-A | v3d manifest SHA256; row identity; band stats | PASS |
| 3D-B | two-arm tables, empirical coverage, no tuning, labelled views | PASS |
| 3D-DQ | coverage void root-caused + disclosed; distance flags not imputed | PASS |

**Known limits for any operator:** (1) 2026 test decay has zero distance
cov; (2) very long horizons 365d are small-cohort; (3) conformal coverage is
temporal/diagnostic, re-measure at deployment; (4) loco-generalization stress
result is reported as a stress, not a production claim. No deep sequence model
is introduced; uncertainty is tree-based split conformal only.