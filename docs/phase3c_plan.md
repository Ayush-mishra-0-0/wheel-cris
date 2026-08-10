# Phase 3C — Segment-Aware, Loco-Conditioned Degradation + Risk

**Status:** Open for execution · governing plan for Phase 3C
**Owner:** Wheel Engineering Intelligence Platform
**Date:** 2026-08-08
**Prerequisite reviews:** 11-point ML Systems & Architecture Review (accepted); lifecycle/identity findings (this phase).

---

## 1. Problem statement

Empirical evidence establishes that `wsmEquipmentId` binds to a **mounted wheel
position (slot)** on a locomotive, not to a physical wheel. Wheel replacements
preserve the equipment identifier while producing persistent upward diameter
step-changes (~1090 mm). A single equipment-ID trajectory therefore stitches
together multiple physical wheels over time.

Consequence already measured in the codebase: the Phase 3B next-state regression
excludes only *turning* resets (`models/phase3b/build_degradation_dataset.py`),
so replacement pairs are treated as ordinary wear. Result
(`models/experiments/v3b/degradation_results.json`): diameter MAE 17.95 mm vs
1.84 mm persistence baseline, R² −0.91. Lifecycle contamination is a primary
suspect for that failure and must be quantified and removed before any
production degradation modelling.

Root/tread semantics are now approved (Q8, 2026-08-08): `wsmRoot1/2` and
`wsmThread1/2` are direct defect-depth measurements, **3 mm = max/condemning,
lower is better** → `root_margin = 3.0 - wsmRoot`, `tread_margin = 3.0 - wsmThread`.

## 2. Objectives

1. Build a **governed lifecycle Event Ledger** that categorizes boundaries into
   CONFIRMED / LIKELY / ANOMALY / UNKNOWN with attached evidence — never a
   single-heuristic auto-CONFIRMED replacement.
2. Quantify lifecycle contamination on the existing v3b pairs (diagnostic only).
3. Materialise **WES v2** with lifecycle identifiers + physical distance tracking.
4. Release a leakage-safe, point-in-time-correct feature substrate feeding two
   **independent** model families: degradation (future engineering state) and
   maintenance risk (event probability). Combine only downstream in the health/index layer.
5. Produce **relative / margin-based RUL** until the official limit register exists.
6. Pin a reproducible Phase 3C benchmark environment.

## 3. Delivery stages and gates

```text
Stage 0  Environment engineering (pin Phase 3C environment)   → gates 3C-0
Stage A  Engineering Event Ledger v1.0 (CONFIRMED/LIKELY/…)   → gates 3C-A
Stage B  Diagnostic replacement-exclusion ablation (v3b)      → memo only
Stage C  WES v2 + segment-aware feature substrate             → gates 3C-C
Stage D  Distance & exposure ablation (diagnostic)            → memo only
Stage E  Degradation model  +  Maintenance-risk model         → independent releases
```

No stage publishes a production artifact until its gate passes. Stages B and D
are diagnostics and never produce the Phase 3C benchmark.

---

## 4. Stage 0 — Reproducible environment engineering

**Context:** original Phase 1/2 experiments ran on an office PC that is not
currently accessible. Execution continues on the personal laptop; this does not
block Phase 3C.

**Findings from repository audit (2026-08-08):**
- No `requirements.txt`, `environment.yml`, `pyproject.toml`, `Pipfile`, or
  lockfile exists anywhere in the repository.
- `README.md` documents only "Python 3.10+, PySpark/pandas, pyarrow".
- No experiment manifest records package versions, Python version, OS, commit,
  or dataset SHA256.
- The office-PC environment is therefore **undocumented**; byte-for-byte
  reconstruction is impossible.

**Decision:** Phase 3C uses a **new pinned benchmark environment** built in the
local `ayush` virtual environment, and is explicitly labelled as such. It is a
fresh isolated environment (no assumption that it matches Phase 1/2).

**Pinned environment record (2026-08-08):**

| Item | Value |
| --- | --- |
| Python | 3.14.2 (tags/v3.14.2:df79316, Dec 5 2025) [MSC v.1944 64 bit (AMD64)] |
| OS | Windows 11 (10.0.26200-SP0), x86-64 |
| CPU/GPU | recorded at first Phase 3C run in `environment.md` |
| Interpreter | `ayush/Scripts/python.exe` |
| Git commit | `git rev-parse HEAD` recorded per run |
| Dataset SHA256 | every Phase 3C dataset carries a manifest SHA256 (existing convention) |

**Procedure:**
1. Install the closest documented stack (Python 3.10+ semantics: pandas,
   pyarrow, numpy, scikit-learn, XGBoost/CatBoost/LightGBM) into `ayush` with
   **exact pinned versions** — no blind upgrade/downgrade.
2. Freeze: `pip freeze > environment/requirements-lock.txt` and write
   `environment.md` capturing python version, OS, CPU/GPU, package versions,
   git commit.
3. Every Phase 3C run records dataset SHA256s in its manifest (existing
   `_sha256` convention in `silver_gold/transform.py`).
4. Reports must state: *"Phase 3C is a new pinned benchmark environment; no
   byte-for-byte reproducibility claim against Phase 1/2 is made."*
5. When office access returns, compare environments **retrospectively only** —
   never a prerequisite for current execution.

**Gate 3C-0:** `environment.md` + `requirements-lock.txt` exist; `python -c
"import pandas, numpy, sklearn, xgboost"` succeeds in `ayush`.

---

## 5. Stage A — Engineering Event Ledger v1.0

### 5.1 Identity ontology

```text
Locomotive
  └── Mounted Position (wsmEquipmentId)   ← identifier persists across wheels
        └── Physical Wheel                ← replaced over time
              └── Inspection Records
```

A lifecycle **segment** is the span of inspections belonging to one physical
wheel within one slot. Replacement events are the segment boundaries.

### 5.2 Event taxonomy and confidence hierarchy

| Event type | Definition | Confidence states | Boundary effect |
| --- | --- | --- | --- |
| replacement | New physical wheel installed; persistent upward diameter jump | CONFIRMED / LIKELY | **segment boundary** |
| turning / reprofiling | Material removed on lathe (`wsmturning=1` owner-confirmed, Q1) | recorded event | **segment boundary** |
| anomaly | Spurious measurement; jump reverts within 1 inspection | ANOMALY | not a boundary |
| unknown | Ambiguous (e.g. flag=2 without persistent jump) | UNKNOWN | not a boundary |

### 5.3 Detection rules (triangulation — no single-signal authority)

A CONFIRMED replacement requires **two or more independent signals**:

1. **Persistent diameter jump** — ΔDia > +10 mm and the new level persists for
   ≥ 2 subsequent inspections (primary physical signal).
2. **`wsmWheelAnalysisFlag = 2`** — treated as **evidence only**, not an
   automatic replacement. Its precision/recall is measured against persistent
   jumps in the validation pack.
3. **Provision-date change** (`wsmProvDate` / provision reference change) —
   corroboration only.

Classification:
- Persistent jump **and** ≥1 corroborator (flag=2 or provision change) → **CONFIRMED**.
- Persistent jump **only** → **LIKELY**.
- Jump reverts within 1 inspection → **ANOMALY**.
- flag=2 or provision change **without** persistent jump → **UNKNOWN** (do not
  force a lifecycle boundary).

### 5.4 Output schema (Engineering Event Ledger)

Per the agreed contract, one record per detected event:

| Field | Description | Example |
| --- | --- | --- |
| `position_id` | Mounted position ID (`wsmEquipmentId`) | 912507 |
| `event_date` | Timestamp of event | 2025-08-17 |
| `event_type` | Detected event taxonomy | replacement |
| `confidence` | CONFIRMED / LIKELY / ANOMALY / UNKNOWN | CONFIRMED |
| `confidence_score` | Algorithmic confidence | 0.99 |
| `old_dia` / `new_dia` | Pre- and post-event diameters | 1056 mm / 1093 mm |
| `persistence` | Number of verified subsequent rows | 6 |
| `loco_id` | Associated locomotive | 37605 |
| `signals` | Which corroborating signals fired | ["persistent_jump", "analysis_flag_2"] |
| `is_lifecycle_boundary` | Whether it starts a new segment | true |

### 5.5 Deliverables

- `configs/engineering_event_ledger_spec_v1.json` — machine-readable contract
  (event taxonomy, rules, confidence definition, validation rules, release status).
- `engineering_layer/build_event_ledger_v1.py` →
  `data/gold/engineering_event_ledger/v1.0/engineering_event_ledger.parquet`
  + manifest (SHA256) + card.
- `validation/event_ledger_validation.md` — evidence pack per
  `validation/README.md` (source snapshot, queries, denominators, exclusions,
  unresolved ambiguity). Includes hand-labelled-sample precision/recall of
  flag=2 → replacement and persistent-jump → replacement.
- Per-(measurement, horizon) capability: `replacement_before_horizon` flag.

**Gate 3C-A:** ledger released, validation pack PASS, no single-signal
CONFIRMED, ANOMALY/UNKNOWN preserved and not treated as boundaries.

---

## 6. Stage B — Diagnostic replacement-exclusion ablation (not the benchmark)

Purpose: quantify how much of the 17.95 mm diameter MAE is lifecycle
contamination.

- **Fixed cohort:** frozen row indices of the existing
  `model_datasets/v3b/degradation_pairs.parquet`; identical test set for both arms.
- **Experiment A:** old v3b training rows (current `crosses_reset` = turning-only).
- **Experiment B:** same rows minus replacement-boundary pairs from the Stage A ledger.
- **Identical** features, splits, seeds, hyperparameters; only the training-row
  exclusion differs.
- Both arms evaluated on **the same test indices**.
- Report per-dimension MAE/RMSE/R² and the fraction of diameter MAE attributable
  to replacement contamination.
- Outcome is a **memo only** (e.g. `models/experiments/v3b/replacement_contamination_memo.md`);
  not released as a benchmark and not consumed as a Phase 3C result.

**Completed 2026-08-09** (see `models/experiments/v3b/replacement_contamination_memo.md`):
on a correctly aligned pipeline the diameter MAE is 4.52 mm, of which 0.38 mm
(8.4%) is attributable to replacement contamination (3,491 training pairs
excluded); the stored 17.95 mm figure is inflated by a feature/target
misalignment in `run_degradation_model.py` (Y/B computed pre-sort, indexed
post-sort) and must be re-derived before being quoted again.

---

## 7. Stage C — WES v2 + segment-aware leakage-safe substrate

### 7.1 WES v2 (new version; WES v1.0 immutable)

Adds to the frozen state layer:

- **Lifecycle identifiers:** `lifecycle_segment_id`, `segment_index`,
  `days_in_segment`, `days_since_replacement`, `replacement_before_horizon`.
- **Physical tracking:** `distance_since_replacement_km`,
  `days_since_turning`, `distance_since_turning_km`.
- **Semantics unblocked:** `root_margin`, `tread_margin`
  (`3.0 - wsmRoot/Thread`, Q8); `wsmWheelAnalysisFlag` (currently absent from
  WES v1.0) preserved as observed context.
- Degradation framing: `wear = f(time, distance, state, operating conditions)`.

Missingness (e.g. ~37% distance, ~82% `distance_since_turning_km`) is preserved
as native-NaN for tree models plus explicit coverage flags — **no imputation**.

### 7.2 Segment-aware degradation substrate

- Grain: consecutive inspection **pairs within a segment**.
- Wear targets exclude pairs crossing **replacement or turning** boundaries.
- `anomaly` / `unknown` rows retained with flags, not silently dropped.
- Materialise approved `interval_distance_km` (owner-signed 2026-08-05) from
  `model_datasets/v2/exposure_features_v2.parquet` keyed on
  `operational_exposure_id`, plus `distance_per_day_km`, `running_days(_pct)`,
  `rtis_distance_coverage_*`, `distance_since_turning_km`.

### 7.3 Point-in-time loco conditioning (leakage prevention)

- Prohibited: lifetime averages computed over the entire dataset.
- Mandated point-in-time (available at prediction timestamp `t`) per-loco
  metrics:
  - cumulative km up to `t`;
  - recent km over the previous 30/90 days;
  - historical wheel-wear rate up to `t`;
  - recent maintenance frequency up to `t`.
- Reuse the existing point-in-time `_ledger_cumsum` / `searchsorted` pattern in
  `model_datasets/build_exposure_features_v2.py:65-97` (day ≤ `t` only).

**Gate 3C-C:** WES v2 manifest + card released; substrate manifests SHA256;
leakage review (no future facts in any feature) PASS.

---

## 8. Stage D — Distance & exposure ablation (diagnostic)

Question: does operational distance explain incremental degradation beyond
current state + calendar exposure?

- Two identical training arms: baseline (no `interval_distance_km`) vs
  + `interval_distance_km`.
- Identical rows, lifecycle segmentation, splits, seeds, features (except
  distance), hyperparameters.
- Evaluate overall + rolling production-sim metrics, stratified by:
  - distance exposure (present / missing, coverage deciles);
  - interval duration bands;
  - interaction metrics `interval_days`, `interval_distance_km`,
    `distance_per_day`.
- Outcome is a memo quantifying the incremental value of distance — **not** the
  final benchmark.

---

## 9. Stage E — Independent model families

### 9.1 Degradation model (future engineering state)

- Predict **change ΔX_dim(Δt)** per dimension (dimension-specific models/heads
  — no monolithic multi-output model), with quantile/conformal uncertainty.
- Derive future state: `X̂(t+h) = X(t) + ΔX̂(h)`.
- Banded evaluation at 30/60/90d using real pairs with Δt ≈ h (see §10) —
  never assume inspections occur exactly at +h.
- Evaluation: chronological split + rolling production simulation + grouped-by-loco
  holdout (proves loco generalization).

### 9.2 Maintenance-risk model (event probability)

- Horizons: **30, 60, 90, 180, 365 days** (60d explicitly added; existing 30/90/180/365 retained).
- Targets: P(turning within H) and a **separate** P(replacement within H) using
  ledger-censored rows (replacement-before-horizon rows are censored/flagged, not
  used as normal future-state targets).
- Metrics: PR-AUC (primary), ROC-AUC, Brier, ECE, Recall@Top-k, rolling stability,
  inspection-capacity analysis. Data (prevalence, stability, calibration, capacity)
  determines operational value — no horizon pre-selected.

### 9.3 Separation of concerns

- Degradation and risk are **independent**, sharing only the leakage-safe
  feature substrate. No single model predicts everything.
- Replacement detection (Stage A) does **not** imply survival censoring
  semantics are solved. Survival results are withheld from production until
  observation-end/censoring semantics are explicitly confirmed with data owners.
- **Relative / margin-based RUL** is the initial output. Engineering RUL
  (`RUL ≈ remaining_margin / predicted_degradation_rate`) is released only once
  the official limit register exists.
- Health index is a **downstream engineering layer** combining predicted
  degradation, current dimensional margins, uncertainty, and maintenance risk —
  never a monolithic training target.

---

## 10. Evaluation windows for irregular inspection cadences

Inspections are not daily (median interval ~75 days, IQR wide). For each horizon
`H`, define a **window** and report cadence honestly:

| Horizon H | Evaluation window | Report |
| --- | --- | --- |
| 30d | real pairs with Δt in [20, 45]d | target horizon, n, median Δt, IQR |
| 60d | real pairs with Δt in [45, 80]d | target horizon, n, median Δt, IQR |
| 90d | real pairs with Δt in [70, 120]d | target horizon, n, median Δt, IQR |
| 180d | real pairs with Δt in [140, 240]d | target horizon, n, median Δt, IQR |
| 365d | real pairs with Δt in [300, 450]d | target horizon, n, median Δt, IQR |

Every report states target horizon, actual Δt distribution, n, median Δt, and
IQR. Results are not compared across horizons without this context.

---

## 11. Guardrails

- Bronze immutable; every transformation reproducible and versioned.
- No feature uses a fact with business time after its score timestamp.
- CONFIRMED lifecycle boundaries require ≥2 independent signals.
- ANOMALY/UNKNOWN events are preserved and never forced into boundaries.
- Blocked values are never silently imputed.
- No monolithic multi-output model; no causal claims from correlations.
- Phase 3C results are reported under the new pinned benchmark environment label.

## 12. Change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-08 | 1.0 | Initial Phase 3C governing plan. Captures lifecycle/identity findings, 11-point review directives, Q8 root/tread semantics, and Stage 0–E delivery sequence. |
