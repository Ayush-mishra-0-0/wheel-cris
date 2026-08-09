# Phase 3C — Clean Degradation Benchmark Re-establishment (Plan)

**Status:** PLAN — approved scope, awaiting implementation go-ahead.
**Date:** 2026-08-09
**Supersedes:** the invalid historical v3b benchmark (17.95 mm MAE) as the
reference for Phase 3C. Stages A/B artifacts remain unchanged as historical
evidence.

---

## 1. Scientific state (authoritative)

The historical v3b result (`models/experiments/v3b/degradation_results.json`):

    Diameter MAE = 17.95 mm, R² = −0.91  →  INVALID benchmark.

Root cause: `models/phase3b/run_degradation_model.py` computed `Y`/`B` on the
wheelset-grouped parquet row order (lines 101-103), then sorted by timestamp
(line 105) and built `X` from the sorted order (110-120) while indexing `Y` with
the sorted positions (121-122) — a feature/target misalignment.

Correctly aligned diagnostic (Stage B):

    aligned v3b ML diameter MAE:     4.52 mm
    replacement-cleaned ML MAE:      4.14 mm
    absolute improvement:            0.38 mm
    relative reduction:              8.4%
    replacement pairs excluded:      3,491

**Critical finding:** persistence MAE ≈ 1.9992 mm. The corrected ML model
currently does **not** beat persistence. This is the most important Stage B
result and the reason the clean benchmark is a gate, not a tuning exercise.

**The scientific question:**

> Can future within-lifecycle wheel engineering-state degradation be predicted
> better than simply assuming that the current state persists?

---

## 2. Guiding principles (from Principal directive)

- **No metric-chasing.** The objective is to establish whether future wheel
  degradation is genuinely predictable beyond strong physical/statistical
  baselines.
- Never use 17.95 mm as a valid result. Quote only as invalid historical
  evidence. Never call the 8.4% reduction causal.
- Alignment safety is a hard requirement (explicit row-identity assertions).
- Preserve every historical experiment; create new versioned artifacts.
- Freeze cohorts, hash datasets, pin environment, report negative results.
- The key metric is **incremental improvement over persistence**, not absolute MAE.

---

## 3. Execution order (approved)

```text
Stage 0  Environment pinning (NEW pinned Phase 3C env, explicit)
Stage A  Event Ledger  [DONE - unchanged]
Stage B  Contamination diagnostic  [DONE - unchanged, memo only]
------------------------------------
Clean benchmark re-establishment  <-- THIS PLAN
  → Persistence baseline (first-class)
  → Historical-rate baseline (point-in-time)
  → Clean ML benchmark (Persistence / Rate / Ridge / XGBoost)
  → Contamination views A & B
  → Distance ablation (controlled, stratified)
  → Decision gate
------------------------------------
Stage C  WES v2 + full segment-aware substrate
Stage E  Independent degradation + maintenance-risk models
         Downstream health/RUL layer
```

---

## 4. Environment pinning (Stage 0 within this plan)

- Create `environment/phase3c.md` recording: OS (win32), Python version,
  CPU, GPU (none), package versions (`xgboost==3.4.0`, `catboost==1.2.10`,
  `lightgbm==4.7.0`, `scikit-learn==1.9.0`, `pandas`, `numpy`, `pyarrow`),
  git commit, dataset SHA256, seed.
- Label Phase 3C explicitly: **NEW PINNED BENCHMARK ENVIRONMENT**. No
  byte-for-byte reproducibility claim vs Phase 1/2. Retrospective comparison
  when office access returns — never blocks current work.

---

## 5. Alignment-safe evaluation core (new)

`models/phase3c/degradation_eval.py`:

- `measurement_record_id` is the **row identity** carried through every sort,
  filter, merge, groupby, reset_index, and split.
- Guard: `assert X_row_ids.equals(Y_row_ids)` before any fit.
- One shared metric routine per dimension: MAE, RMSE, R², Spearman, N.
- One shared chronological split routine that returns the **same frozen test
  indices** to every caller.
- A persistence scorer (current state as prediction vs next within-life target)
  and the historical-rate scorer.

## 6. Alignment regression test (new)

`models/phase3c/alignment_safety_test.py` (pytest-compatible + standalone):

1. Build X/Y with known `measurement_record_id`.
2. Reorder one side.
3. Show positional indexing silently yields wrong labels.
4. Assert the guard detects the mismatch (test fails without the guard).
5. Include a positive case: aligned path passes.

## 7. Clean benchmark substrate (new)

`models/phase3c/build_clean_benchmark_substrate.py` →

`model_datasets/v3c/clean_benchmark_pairs.parquet` + manifest (SHA256) + card.

- Base: `model_datasets/v3b/degradation_pairs.parquet` (feature parity; no rebuild).
- Add from the governed **Event Ledger**:
  - `crosses_replacement` — ledger `replacement` event strictly inside
    `(measurement_timestamp, next_time]` for the same wheelset;
  - `lifecycle_segment_id` — segment between replacements per wheelset;
  - `replacement_before_horizon` where applicable (point-in-time).
- Add from `model_datasets/v2/exposure_features_v2.parquet` joined via
  `operational_exposure_id` (`OE-<measurement_record_id>-<next_record_id>`,
  ~50% coverage): `interval_distance_km`, `distance_per_day_km`,
  `rtis_distance_coverage_pct_in_interval`, `distance_since_turning_km`,
  plus an explicit `distance_available` flag.
- Keep `crosses_reset` (turning) respected.
- **Clean within-lifecycle cohort:** `~crosses_reset & ~crosses_replacement`.
- UNKNOWN/ANOMALY events preserved; never coerced into CONFIRMED boundaries.

## 8. Frozen evaluation cohort (new)

`model_datasets/v3c/clean_benchmark_cohort.parquet` — immutable manifest of row
IDs, split definition, timestamps, dataset SHA256, feature list, target
definition, seed, model config. All benchmark arms consume the same frozen test
indices. No experiment may regenerate a different test cohort.

## 9. Experiments (in this order)

### 9.1 Persistence baseline (first-class)
Per dimension: prediction = current measured state; target = next valid
within-lifecycle measurement. Report MAE, RMSE, R², Spearman, N.

### 9.2 Historical-rate baseline (new, point-in-time)
`predicted_delta = historical_wear_rate × future_interval`, where rate =
`cumulative_valid_wear / cumulative_valid_exposure` (days when distance absent,
km when present), strictly from data available at time `t` (reuse the
`_ledger_cumsum`/`searchsorted` pattern in
`model_datasets/build_exposure_features_v2.py:65-97`). No future data. If a
wheel has no prior history at `t`, fall back to persistence.

### 9.3 Clean ML benchmark
Models: Persistence, Historical-rate, Ridge (linear), XGBoost (one strong tree;
fixed defaults, no broad tuning). Identical rows, split, test cohort, target,
evaluation code, seeds, hyperparameters. Report per dimension MAE/RMSE/R²/
Spearman/N **and** improvement over persistence and historical-rate.

### 9.4 Contamination views (Stage B, kept diagnostic)
- **View A** — same frozen test cohort; isolate the effect of removing
  replacement-contaminated training examples (A = aligned v3b rows incl.
  replacement pairs in train; B = minus those pairs).
- **View B** — genuinely clean within-lifecycle test cohort.
- Label both explicitly; never select whichever produces the better number.

### 9.5 Distance ablation (controlled; only after 9.1-9.4)
- Arm A: lifecycle + time/current-state features, NO `interval_distance_km`.
- Arm B: identical + `interval_distance_km`.
- Everything else identical (rows, lifecycle segmentation, test set, split,
  seed, model, hyperparameters, target).
- Report MAE/RMSE/R², absolute + percentage improvement.
- Stratify by: distance present vs missing; `interval_days` bands;
  `interval_distance_km` bands; `distance_per_day_km` bands; RTIS coverage;
  coverage deciles.

### 9.6 Interaction analysis (no dozens of features)
Inspect at minimum:
- `interval_days × interval_distance_km`
- `distance_per_day_km × interval_days`
- `current_state × interval_distance_km`

## 10. Dimension-specific modelling

Separate models per dimension (diameter, flange thickness, root, gauge) sharing
the leakage-safe substrate. No monolithic multi-output model. It is acceptable
— and scientifically useful — if one dimension is predictable and another is not.

## 11. Irregular-cadence honesty

Inspection median interval ≈ 75 days. Every horizon/analysis reports intended
horizon, actual Δt distribution, N, median Δt, IQR, and tolerance window. No
"90-day prediction" claims without the actual Δt context.

## 12. Guardrails (enforced)

- No future information in any aggregate; point-in-time only.
- No hyperparameter tuning beyond fixed defaults.
- No dashboard/frontend; no absolute RUL claims; no survival claims.
- `wsmWheelAnalysisFlag=2` is evidence, not an authoritative replacement label
  (precision ≈ 16.2%); never force ambiguous upward movements into boundaries.
- If clean ML ≤ persistence: stop feature expansion, investigate the
  information bottleneck (measurement variability, cadence, latent maintenance,
  exposure heterogeneity), and report that as the scientific finding.

---

## 13. Files (smallest set)

**New (code):**
- `models/phase3c/degradation_eval.py` — alignment-safe eval core.
- `models/phase3c/alignment_safety_test.py` — regression test.
- `models/phase3c/build_clean_benchmark_substrate.py` — substrate + manifest.
- `models/phase3c/run_clean_degradation_benchmark.py` — persistence → rate →
  Ridge → XGBoost; contamination views; distance arms; stratification.

**New (data/artifacts):**
- `model_datasets/v3c/clean_benchmark_pairs.parquet` + `_manifest_v1.0.json`.
- `model_datasets/v3c/clean_benchmark_cohort.parquet`.
- `models/experiments/v3c/clean_degradation_benchmark_results.json`.
- `models/experiments/v3c/clean_degradation_benchmark_report.md`.

**Modified:**
- `docs/phase3c_plan.md` — corrected narrative + new gate section.

**Untouched (historical evidence):**
- `models/phase3b/run_degradation_model.py`
- `models/experiments/v3b/degradation_results.json`, `degradation_report.md`
- `models/experiments/v3b/replacement_contamination_*`
- All `model_datasets/v3b/*`, all `models/experiments/v1.x`, `v2`, `v3`.

---

## 14. Gate definition

**Decision gate: does the clean ML system beat persistence and/or the
historical-rate baseline by a meaningful and stable margin?**

- **NO** → stop feature expansion; investigate the information bottleneck.
- **YES** → proceed to deeper feature engineering, loco conditioning,
  distance/track exposure, uncertainty, and eventually health/RUL.
