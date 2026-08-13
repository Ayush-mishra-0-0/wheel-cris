# Phase 3F — Change-Space Degradation-Dynamics Benchmark

**Status:** Open for execution · governing plan for Stage F
**Owner:** Wheel Engineering Intelligence Platform
**Date:** 2026-08-10
**Prerequisite:** Phase 3E substrate
(`model_datasets/v3e/forecast_information_ladder.parquet`), frozen chronological
cohort, pinned environment (`ayush`).

---

## 1. Framing — why change space, why now

Phase 3D/3E evaluated forecasts on the **absolute next state**
`X̂(t+H) = X(t) + ΔX̂(H)`. A level-target benchmark cannot prove the model learns
degradation dynamics: the degradation signal over 30–90 days (mean ΔX ≈ −0.5 to
−1.4 mm for diameter) is tiny relative to the ~1050 mm level, so *persistence*
(`X̂ = X(t)`) is nearly unbeatable on level MAE. Measured on the v3e test cohort,
persistence beats every ML arm on `wsmDia` level MAE at 30/60/90d.

Phase 3F therefore forecasts **the change itself**:

```
ΔX = X_future − X_current          (per dimension, mm)
```

Here persistence ⇒ ΔX = 0, and any model must earn its margin against three
explicit baselines. This is the frame in which "learns degradation dynamics"
is distinguishable from "copies the last measurement."

## 2. Explicit hypotheses tested (Phase 3F answers)

H1. **Baseline-dominance:** some model predicts ΔX better (MAE/RMSE/Spearman)
    than zero-change, population drift, and the per-wheelset historical rate.

H2. **Horizon scaling:** predicted |ΔX| grows with H (30/60/90/180/365d), i.e.
    the model learns a *rate*, not a fixed offset.

H3. **Exposure scaling:** predicted ΔX scales with `interval_distance_km` /
    `distance_per_day_km`, matching the observed relationship.

H4. **Direction & magnitude fidelity:** predicted ΔX preserves wheel-specific
    sign (on |ΔX| beyond measurement noise) and does not collapse toward the
    population mean.

H5. **Variance reproduction:** predicted ΔX distribution matches observed
    degradation variance (not shrunk 3× toward the mean as Phase 3E showed).

H6. **Transferability:** any gain survives grouped-by-loco holdout (never-seen
    locomotives), reported as a stress, not a promise.

If **no** model beats zero-change or the historical-rate baseline, that is the
honest result: the available trajectory may not contain predictable degradation
dynamics at these horizons. No tuning is performed to force a win.

## 3. Scope

- Change-space degradation forecast only. The maintenance-risk family stays v3a.
- One model per (dimension), gradient boosting, no deep sequence models
  (per approval — first establish whether the trajectory contains dynamics).
- Feasible entirely on frozen v3e inputs; no new ingestion.
- **All five horizons are evaluated** (30/60/90/180/365d). No production horizon
  is selected by this phase; 180d/365d are reported with their small-n caveats.

## 4. Deliverables

```text
docs/phase3f_plan.md                                   (this plan)
models/phase3f/build_change_space_dataset.py
  -> model_datasets/v3f/change_space_benchmark.parquet  (+ SHA256 manifest)
models/phase3f/run_change_space_dynamics.py
  -> models/experiments/v3f/change_space_dynamics_results.json   (frozen split)
models/phase3f/run_change_rolling_sim.py
  -> models/experiments/v3f/rolling_change_sim_results.json      (PRIMARY)
models/phase3f/run_change_loco_holdout.py
  -> models/experiments/v3f/change_loco_holdout_results.json     (transferability)
models/experiments/v3f/quality_gate_report.md
```

## 5. Stage 3F-A — Change-space substrate (v3f)

- Anchor: the **within-lifecycle** v3e row set (239,684 rows), same order, same
  `measurement_record_id`. No re-splitting.
- Add per dimension `dX_{d} = target_{d} − base_{d}` (mm), the phase target.
  Sign convention preserved: diameter/root decrease with wear, gauge/flange
  drift as observed.
- Censoring flags inherited unchanged: `replacement_before_{H}d`,
  `crosses_replacement`, lifecycle segment ids. Rows are flagged, never dropped.
- Coverage flags inherited: `distance_available`; native NaN preserved, no
  imputation.

**Gate 3F-A:** manifest SHA256; row-identity assertion (v3e ↔ v3f same ids,
same order); dX summary stats per dimension/band recorded.

## 6. Stage 3F-B — Frozen-split change benchmark (deterministic frame)

Same rows / splits / seeds / hyperparameters across every arm.

### Baselines (must each be reported)
- **B0 zero-change:** ΔX̂ = 0.
- **B1 population drift:** per (dimension, band), train-period mean ΔX / mean
  interval_days scaled by each row's own `interval_days` (a mean degradation
  rate model). Falls back to 0 when the band has no train rows.
- **B2 per-wheelset historical rate:** point-in-time cumulative
  ΔX/day(t) from the wheel's OWN prior within-life intervals (reusing the 3C
  `add_historical_rate_predictions` core), projected by `interval_days`. Falls
  back to 0 with no prior valid interval.

### Model arms (identical rows, fixed HP)
- **M3 = trajectory:** state + quality + lifecycle + trajectory
  (30/90/180d changes & rates) + distance history.
- **M4 = + operational context:** M3 + categoricals (shed, position, defect) +
  maintenance/RTIS counts. (The Phase 3E winner; the lead arm.)
- Predicting `dX_{d}` directly (target = change, not level). `interval_days` and
  `horizon_days` remain continuous features; the model is band-invariant, only
  *evaluated* per band.

### Diagnostics per (dimension, band, view, arm)
- MAE / RMSE / R² / Spearman on ΔX.
- **Signed bias** `mean(ΔX̂ − ΔX)`.
- **Sign accuracy** on meaningful-change rows (`|ΔX| > noise floor` per dim).
- **Variance fidelity:** `std(ΔX̂) / std(ΔX)` (Phase 3E showed ~0.34 shrinkage;
  a dynamics model must not collapse).
- **Horizon scaling:** mean |ΔX̂| per band vs mean |ΔX| per band.
- **Exposure scaling:** Spearman(ΔX̂, interval_distance_km) and
  Spearman(ΔX̂, distance_per_day_km) vs the same for observed ΔX.
- Views: full_test, distance_present, distance_missing, coverage_restricted
  (≤2025-12-31) — labelled, never pooled indistinguishably.

### Uncertainty
- **Split conformal on ΔX** (calibration = last 10% of chronological train
  rows, never test), 80% and 95%. Reported as **empirical temporal coverage**,
  an observed diagnostic, not a guarantee.

**Gate 3F-B:** JSON written; arm-vs-baseline table; no tuning; env/SHA recorded.

## 7. Evaluation hierarchy (inherits §6 of the 3D plan)

1. **Rolling production simulation = primary deployment evidence**
   (monthly point-in-time refits, no future facts).
2. **Grouped-by-loco holdout = generalization stress** (~20% of wheelsets
   held out; reported as a stress; failure reported, not hidden).
3. Frozen chronological split = deterministic secondary frame.

## 8. Guardrails

- No future facts in any feature; no exact-handle timestamps.
- No imputation of distance or state; labelled views only.
- No monolithic multi-output; no deep sequence; no tuning to force a win.
- Conformal coverage = empirical temporal coverage, not a guarantee.
- Honest reporting: if ML loses to zero-change / historical rate, that is the
  finding. "The goal is to determine whether our data contains enough
  information to forecast how much and in which direction a wheel will change
  over 30/60/90 days."
- No production horizon selected; 180d/365d reported with small-n caveats.

## 9. Change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-10 | 1.0 | Initial Phase 3F plan. Change-space target; three baselines; explicit H1–H6; variance/horizon/exposure fidelity diagnostics; conformal on ΔX; rolling primary; loco stress; no deep sequence. |
