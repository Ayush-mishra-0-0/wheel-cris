# Railway Wheel Engineering Intelligence Platform

An engineering-intelligence platform that reconstructs the lifecycle of railway wheels and wheelsets, detects abnormal wear, estimates remaining useful life (RUL), and recommends defensible maintenance action — with explainable "likely contributing factors" instead of black-box predictions.

> **Standing:** Bronze → Silver → Business Truth → Inspection Intervals → Operational Exposure → Feature Store are **released and validated for the WAP7 fleet**. Health scoring, ML and RUL are deliberately **blocked** until two release gates pass: physical-distance (RTIS km) semantics and wheel degradation/wear business rules.

## Problem statement

Fuse multi-source data — wheel measurements, maintenance history, locomotive behaviour, operational/route (RTIS/FOIS) data, and failure history — to:

- reconstruct each wheel's life (identity → inspection → turning/replacement);
- detect **abnormally fast wear** and flag wheels for inspection;
- explain **likely contributors** (wheel history, maintenance, operation, route, environment) with uncertainty, never false certainty of cause;
- predict RUL and recommend prioritised, evidence-led maintenance action.

## Platform architecture

```text
Bronze (immutable source snapshots)
  -> Silver (standardised, quality-flagged records)
  -> Business Truth v1.0 (point-in-time wheel -> equipment -> locomotive assignment)
  -> Inspection Intervals v1.0 (validated temporal boundaries)
  -> Operational Exposure (interval-linked events; distance blocked)
  -> Feature Store v1.0 (governed, spec-driven feature layer)
  -> Engineering Layer: Identity | State | Exposure | Behaviour | Degradation
                      | Maintenance | Health | Prediction | Decision
  -> ML models (later) -> Future Digital Twin (streaming, physics, learning)
```

Everything is versioned and auditable: every derived value traces to source records via lineage, quality gates, and point-in-time correctness. **Gold** is the technical storage tier; products are named by the engineering question they answer (Business Truth, Inspection Intervals, Operational Exposure, Engineering Features, Feature Store, Wheel Health Snapshot, Decision Products).

## Repository layout

| Path | Purpose |
| --- | --- |
| `data/` | Bronze/Silver/Gold datasets (not in git — reconstructed by pipeline; `data.zip` is a local backup) |
| `configs/` | Machine-readable contracts: feature specification, interval/timeline/exposure contracts |
| `sql/` | Source discovery, extraction, and validation queries |
| `silver_gold/` | Bronze→Silver→Gold pipeline scripts (timeline, intervals, exposure, validation) |
| `feature_store/` | Spec-driven feature-store builder + released v1.0 store |
| `validation/` | Formal evidence packs (identity, temporal integrity, business rules, join coverage) |
| `docs/` | Semantics (degradation, RTIS distance), distance-recovery plan, research backlog, status table |
| `reports/` | Immutable data-quality/lineage reports + `plots/{v1.0,v1.1,compare}/` model charts |
| `releases/` | Release notes per product/version |
| `tests/` | Pipeline tests |

## Current status

**Released & validated (WAP7 cohort, 2,317 locos):**

- Business Truth v1.0 — **271,350 / 319,707** measurements (84.87%) with exactly one valid assignment interval (Gold-B); exclusions retained for audit.
- Inspection Intervals v1.0 — **225,262** valid intervals; Engineering Truth validation verdict: **PASS WITH KNOWN LIMITATIONS**.
- Operational Exposure v1.0 — interval-linked RTIS event/job-card/report context; physical distance remains null (`BLOCKED_PENDING_SOURCE_CONFIRMATION`).
- Feature Store v1.0 — 7 features admitted, 7 excluded by contract.

**Blocked / gated (release gates):**

- `interval_distance_km` — RTIS daily-aggregation rule awaits source-owner approval; alternatives tested and rejected (`MovementRegister`), FOIS GPS empty.
- `wear_rate_mm_per_day`, `wheel_health_index` — need engineering sign-off on measurement units, turning/reprofiling reset rules, condemning limits.
- Track geometry (curve/gradient severity) — no authoritative source acquired yet (principal external-data gap; IR Geoportal candidate).
- ML / RUL — no models trained; first agreed target is **abnormally-high-wear detection** with a baseline + explainable model.

Full status: see `docs/project_status_table.md`.

## Getting started

```text
1. Reconstruct data: run Bronze -> Silver -> Gold pipeline scripts (silver_gold/) against source extracts (sql/extraction/).
2. Validate: run tests/ and review validation/ evidence packs.
3. Feature store: build from configs/engineering_feature_specification_v1.json via feature_store/feature_store_builder.py.
```

Requirements: Python 3.10+, PySpark/pandas, pyarrow (see `notebooks/` and `silver_gold/` scripts for imports).

## Guardrails

- Bronze is immutable; every transformation is reproducible and versioned.
- Features are released only through the machine-readable specification — blocked features are never silently imputed.
- No causal claims from correlations: outputs are phrased as "likely contributors" and inspection recommendations, not diagnoses.
- ML consumes Feature Store outputs only — never raw Bronze/Silver/Gold-C.

## Key documents

- `plan.md` — direction, delivery levels/phases, decision gates, implementation status.
- `validation/engineering_truth_validation.md` — Engineering Truth release verdict and limitations.
- `docs/degradation_semantics.md` — field-by-field wheel-measurement semantics and open domain-owner questions.
- `docs/rtis_semantics.md`, `docs/rtis_distance_semantics.md`, `docs/distance_recovery_plan.md` — distance evidence and recovery.
- `docs/feature_readiness_catalog.md`, `configs/engineering_feature_specification_v1.json` — feature release register.
- `docs/project_status_table.md` — senior-level status tracker (problem / input / remarks / PDC).
