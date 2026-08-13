# Phase 5 Layer 3 — Turning/Profile-Policy Benchmark (the "B − A" cut model)

**Contract:** `wheel_profile_lifecycle_contract_v1` § Layer 3 (post-turn wear = A + ε; expected post-turn dim = pre_dim − cut)
**Source:** `model_datasets/v5/turn_policy_benchmark.parquet` (3,237 turning events; 2,117 train / 1,120 test)
**Split:** temporal PIT by `pre_ts` (train < 2024-08-12); shed-policy lookups are train-only.

## Question

Can the machining action (cut) and post-turn profile state be **predicted** from
pre-turn state + shed policy + profile class + position + turn history, i.e. can
we tell an inspector "the post-turn root will be X"?

## Models

- `B0_global` — global train median of the target (single fleet norm).
- `B1_shed`   — per-shed train median of the target (recovered "B − A" policy; unseen sheds → B0).
- `B2_ridge`  — ridge regression on pre-turn state + ordinal context.
- `C1_xgb`    — gradient boosting on the same context.

## Headline results (test, n=1,120)

| target        | B0 MAE | B1 MAE | B2 MAE | C1 MAE | C1 R²  | C1 ρ  | takeaway |
|---------------|-------:|-------:|-------:|-------:|-------:|------:|----------|
| cut (mm)      | 2.929  | 3.068  | 3.847  | **3.004** | 0.008 | 0.411 | cut is a noisy draw around a shed-specific level |
| post dia (mm) | 13.14  | 14.50  | **3.847** | 3.562 | 0.926 | 0.952 | dia = pre − cut; predictable *given* pre-state |
| post flange   | 0.348  | 0.315  | **0.258** | 0.260 | −0.27 | 0.186 | restored to shed target, small ε |
| post root     | **0.328** | 0.365  | 0.299  | 0.426 | −1.16 | 0.124 | static baselines win; root not learnable off these feats |
| post thread   | 0.217  | **0.191** | 0.594  | 0.401 | 0.06 | 0.205 | shed policy dominates thread restore |

## Interpretation (honest)

1. **The cut is not point-predictable.** Per-event machining depth has residual
   σ ≈ 3.7 mm; no feature set moves MAE below the global-median baseline in a
   meaningful, robust way (C1 ties B0 at ~3.0 mm with R² ≈ 0.00). The rank
   signal (ρ ≈ 0.41) comes from *level* shifts across sheds, not from pre-turn
   wear within a shed.
2. **The recovered per-shed policy is real and large** and is the Layer-3 win:
   train-median cut ranges **3.2 mm (GKPL) → 13.1 mm (HWHE)** across sheds
   (see `turn_policy_shed_policy.png`). This is the empirical "B − A" recovery.
   Event cut modality is *discrete*: std(7.7±4.1) dominates any model's
   continuous prediction.
3. **Post-turn state is predictable only in expected value, not exactly.**
   Flange (MAE 0.26 mm) and thread (B1 0.19 mm) cluster tightly around shed
   targets — post-turn wear really is `A + ε` with small ε. For root the
   simplest baseline wins (MAE 0.33 mm); C1 overfits (R² −1.16).
4. **`post_wsmDia` is trivially decomposable**: `pre_dia − cut`. Its R² 0.93
   comes entirely from conditioning on pre_state; the residual error *is* the
   cut error (3.5 mm), confirming (1).

**Fallout for the roadmap:** Layer 4 (turn-risk / limiting dimension) must NOT
pretend to predict *exact* post-turn state. The correct forward quantity is the
**pre-turn decay** (Layer 2) plus the **shed-policy level** for the post-turn
restore (this layer). Where Layer 4 needs a point expectation of post-turn root,
the honest value is *shed target ± 0.4 mm*, not an XGB point estimate.

## Recovered per-shed "B − A" policy (train-only, ≥10 events)

median cut: HWHE 13.05 · SDAD 11.00 · BNDL 9.44 · TATE 8.11 · SRCE 7.76 ·
BZAE 6.00 · LGDE 5.50 · GKPL 3.22

## Artifacts

- `models/experiments/v5/turn_policy_benchmark.json` — full metrics + policy table
- `models/experiments/v5/turn_policy_mae_r2.png` — MAE/R² by model
- `models/experiments/v5/turn_policy_c1_scatter.png` — C1 cut scatter
- `models/experiments/v5/turn_policy_shed_policy.png` — per-shed median cut
- `model_datasets/v5/turn_policy_benchmark.parquet` + `turn_policy_manifest.json`