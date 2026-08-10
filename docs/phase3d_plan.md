# Phase 3D — Horizon-Windowed Future-State Forecasting

**Status:** Open for execution · governing plan for Stage E (degradation forecast)
**Owner:** Wheel Engineering Intelligence Platform
**Date:** 2026-08-09
**Prerequisite:** Phase 3C substrate (`model_datasets/v3c/clean_benchmark_pairs.parquet`), Event Ledger v1.0, frozen chronological cohort, pinned environment (`ayush`).

---

## 1. Framing (per approval 2026-08-09)

Phase 3D is **horizon-windowed future-state forecasting**, explicitly **not**
exact 30/60/90-day forecasting. Inspections are irregular (median ~75d). For
each nominal horizon `H` we forecast `X̂(t+H) = X(t) + ΔX̂(H)` but **evaluate and
report on real within-life inspection pairs whose actual `interval_days` falls
inside the window** of §10 of the 3C plan:

| Horizon H | Evaluation window | Report |
| --- | --- | --- |
| 30d | Δt in [20, 45] | target horizon, n, median Δt, IQR |
| 60d | Δt in [45, 80] | target horizon, n, median Δt, IQR |
| 90d | Δt in [70, 120] | target horizon, n, median Δt, IQR |
| 180d | Δt in [140, 240] | target horizon, n, median Δt, IQR |
| 365d | Δt in [300, 450] | target horizon, n, median Δt, IQR |

Every result carries target horizon, actual Δt distribution (n, median, IQR).
No cross-horizon comparison without that context.

## 2. Scope

- Degradation forecast only. The maintenance-risk family stays v3a (unchanged).
- **No deep sequence models** in this phase. Per-dimension gradient boosting
  (one model per dimension, no monolithic multi-output), matching the 3C
  alignment-safe core.
- Feasible entirely on frozen inputs — no new ingestion.

## 3. Deliverables

```text
models/phase3d/build_forecast_horizon_dataset.py
  -> model_datasets/v3d/forecast_horizon_benchmark_pairs.parquet  (+ SHA256 manifest)
models/phase3d/run_forecast_benchmark.py
  -> models/experiments/v3d/forecast_benchmark_results.json
models/phase3d/run_rolling_forecast_sim.py
  -> models/experiments/v3d/rolling_forecast_sim_results.json
models/phase3d/run_loco_holdout.py
  -> models/experiments/v3d/loco_holdout_results.json
  -> models/experiments/v3d/quality_gate_report.md
```

## 4. Stage 3D-A — Horizon-window substrate (v3d)

- Anchor: `within_lifecycle` rows of the 3C substrate (239,684 rows). Preserve
  `measurement_record_id`, frozen cohort split, row identity throughout.
- Assign each pair exactly one horizon band via nearest-nominal-`H`
  tie-broken to the smaller `H`; pairs not falling in any window are band
  `other` (train-only, never forecast-evaluated).
- Added: `horizon_window` (30/60/90/180/365/other), `horizon_days` (nominal
  H), `interval_days` unchanged; `replacement_before_horizon` per window from
  Event Ledger (CONFIRMED+LIKELY replacement strictly inside
  `(t, t+H]`) — censoring flag, never silently dropped rows.
- Target/base per dimension: reuse the 3C `add_targets_and_bases` rule
  (mean of both valid sides, else the single valid side, else NaN).
- Coverage unchanged: `distance_available` flag + native NaN preserved,
  **no imputation**.

**Gate 3D-A:** manifest SHA256; row-identity assertions pass (same ids in
same order as v3c within-life set); band counts + Δt stats recorded.

## 5. Stage 3D-B — Forecast benchmark (two explicit arms)

Two model arms on **identical rows, split, seeds, hyperparameters**:

- **Arm A — time/state-only**: state, quality codes, exposure, categorical.
- **Arm B — +distance**: Arm A + `interval_distance_km`, `distance_per_day_km`,
  `rtis_distance_coverage_pct_in_interval`, `distance_since_turning_km`,
  `distance_available`.

Forecast: `ΔX̂(H)` predicted as change over the paired interval (actual Δt in
band) with `interval_days` as a continuous feature; derive
`X̂(t+H) = X(t) + ΔX̂(H)`.

### Baselines
- **persistence** (`X̂ = X(t)`)
- **historical-rate / trajectory baseline** (point-in-time per-wheelset
  cumulative rate `ΔX/day(t)` from prior within-life intervals; projected via
  banded Δt; falls back to persistence with no prior valid interval).

### Uncertainty
- **Split conformal** prediction intervals: fit on the train fit-set, calibrate
  width on the **last 10% of the chronological train** (before the frozen
  test cohort), 80% and 95% nominal levels.
- Coverage is reported as **empirical temporal coverage on the held-out test
  set** — an observed diagnostic, **not** an unconditional guarantee.
- Secondary sanity column: native quantile-GBT 0.1/0.5/0.9 for comparison.

### Reporting (per dimension, per band, per arm)
- MAE / RMSE / R² / Spearman / n, median Δt, IQR.
- Empirical coverage and mean interval width (80%, 95%) on:
  1. full frozen test cohort;
  2. **distance-present** subset (`distance_available == True`);
  3. **coverage-restricted** slice (measurements ≤ 2025-12-31, the RTIS
     ledger end — labelled clearly, never merged indistinguishably).

**Gate 3D-B:** JSON written; two-arm table diff; no tuning; env/SHA recorded.

## 6. Evaluation hierarchy (per approval)

1. **Rolling production simulation is the primary deployment evidence.**
2. **Grouped-by-loco holdout is a generalization stress test** (a ~20% loco
   subset held out; reported as such; failure to generalize is reported, not
   hidden).
3. Grouped-by-loco holdout is reported; monolithic freezing chronological split
   is the secondary frame only.

## 7. Guardrails (inherit §11 of 3C)

- No future facts in any feature; no aspiration of exact-handle timestamps.
- No block-level imputation; coverage-restricted and distance-present subset
  never pooled without labels.
- No monolithic multi-output; no causal claim.
- Conformal coverage reported as empirical temporal coverage, not a guarantee.
- Rolling sim is primary; loco test stress; strict split is secondary.

## 8. Change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-09 | 1.0 | Initial Phase 3D governing plan. Horizon-windowed framing, two arms, historical-rate baseline, empirical temporal coverage, rolling primary, loco stress, no deep sequence. |