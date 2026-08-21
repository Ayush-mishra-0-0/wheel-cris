# Distance serving-gate decision (reconfirmation 2026-08-21)

Status: **`interval_distance_km` and its derivatives are APPROVED and RELEASED
to the serving path.** This document is the single authority for the distance
gate; where older documents disagree, this record wins.

## What is released

| Feature | In serving? | Evidence |
|---|---|---|
| `interval_distance_km` | source (substrate/exposure) | owner-APPROVED 2026-08-05 (`architecture/phase2_architecture.md`: "RTIS daily-distance aggregation is owner-APPROVED: interval_distance_km may be materialised"; status BLOCKED → READY_FOR_MATERIALISATION) |
| `km_last_30d/90d/180d` | YES - degradation, wear_rate, pturn `features.json` | verified 2026-08-21 against `models/phase5/serving/*/features.json` |
| `distance_per_day_km` | YES - degradation, wear_rate | same |
| `distance_since_turning_km` | YES - degradation, wear_rate, pturn | same |

All three serving model feature sets were audited directly (num_feats listing):
distance-derived columns are training/serving inputs today and have been since
the phase-5 serving build. The models are trained ON these features; removing
them would be a retraining event, not a config flip.

## What remains blocked / NOT released

1. **mm/km wear rate as a label** — still gated by `degradation_semantics.md`
   (requires turning-reset rule + unit confirmation). Distance availability
   alone does not release it.
2. **Open-data / FOIS map-matched distances** (`distance_recovery/`) —
   `EXPERIMENTAL_NOT_RELEASED`; validation cross-check only.
3. **MovementRegister meter fields** — rejected as a distance ledger
   (`distance_recovery_plan.md`).
4. **GPS geodesic estimates** — never releasable as `distance_km`.
5. **Track geometry (curvature/gradient)** — future work.

## Coverage caveat (honest)

Attributable-distance coverage is partial (~53% of intervals carry approved
distance; `km_*_available` flags exist in the substrate). Serving treats
distance features as NaN-native; ranking/forecast quality where distance is
missing degrades gracefully rather than failing. The planned v1.1 benchmark
rerun should report distance-available stratification alongside existing cuts.

## Reconciled stale references (updated to point here)

- `action_plan_reconciliation_2026-08-19.md` priority 4 / open threads
  ("blocked on RTIS/chainage path") — superseded: the RTIS-safe rule IS the
  approved path; remaining open item is only coverage improvement.
- `candidate_feature_matrix_v2.md`, `feature_readiness_catalog.md`
  ("BLOCKED / unresolved") — pre-approval text, kept for history.
- `ml_correctness_analysis.md` "Distance gate ambiguity" — resolved by this
  document.
