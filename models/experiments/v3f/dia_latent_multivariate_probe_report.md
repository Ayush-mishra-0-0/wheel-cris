# Multivariate latent/mixed-effects `wsmDia` probe — Phase 3F diagnostic

**Date:** 2026-08-11 · **Status:** FALSIFIED (one marginal 90d holdout cell)
**Experiment:** `models/phase3f/run_dia_latent_probe.py`
**Output:** `models/experiments/v3f/dia_latent_multivariate_probe.json`

## Protocol (as specified)

Target `dX_wsmDia = target − base` (mm) at 30/60/90d on the **frozen v3f
chronological split**. Diameter treated as a **noisy observation** — never its
own clean Δ; always paired with root/flange geometry at `t`. All features
point-in-time (state at `t`, `interval_days`, `days_since_turning`,
`days_since_segment_start`, `wheel_age`, `turning_record_at_measurement`,
`lifecycle_segment_id`, distance availability + km; wheel-level slope =
cumulative rate from the wheelset's *own prior pairs only* —
`add_historical_rate_predictions`). No future info. No tuning (fixed XGBoost
250/6/0.1, seed 42, matching M4 codebase). No deep sequence models.

Arms: `A1` dia-only, `A2` +root, `A3` +flange, `A4` +root+flange,
`A5` +lifecycle/turning/distance, `A6` +wheel random-slope proxy. Baselines
`B0` zero-change, `B1` population drift, `B2` historical-rate. `M4_ref` = full
Phase 3E operational feature set on the same split (cross-checked: MAE matches
committed 3F results exactly).

## 1. In-cohort frozen test — dX space (MAE, mm)

| band | B0 | B1 | B2 | A1 dia | A2 +root | A3 +flange | A4 +both | A5 +ctx | A6 +slope | M4 |
|---|---|---|---|---|---|---|---|---|---|---|
| 30d | **1.59** | 2.11 | 2.21 | 3.07 | 2.88 | 2.63 | 2.56 | 3.09 | 3.01 | 2.15 |
| 60d | **1.73** | 2.36 | 3.29 | 2.87 | 2.77 | 2.50 | 2.46 | 2.92 | 2.86 | 2.23 |
| 90d | **2.89** | 4.09 | 9.29 | 3.60 | 3.49 | 3.24 | 3.21 | 3.58 | 3.52 | 3.25 |

**zero-change wins at every horizon.** No arm — including full M4 — beats B0.

## 2. Cross-dimensional gain is real but below the decision line

Spearman on dX, test set (A1 → A2 → A3 → A4):

| band | A1 dia | A4 +root+flange |
|---|---|---|
| 30d | 0.03 | 0.09 |
| 60d | 0.04 | 0.06 |
| 90d | 0.00 | **0.17** |

Root+flange geometry clearly carries an **incremental** diameter signal at 90d
(MAE 3.60 → 3.21, ρ 0.00 → 0.17). But it is far below what is needed to beat
zero-change, and floors are symmetric: var_fidelity ≈ 0.5, sign-acc ≈ 0.85.

## 3. Holdout stress (never-seen wheelsets, 20% by seed 42)

| band | B0 | B2 | A4 | A5 |
|---|---|---|---|---|
| 30d | **2.99** | 9.82 | 3.62 | 3.28 |
| 60d | **3.01** | 17.19 | 3.74 | 3.36 |
| 90d | 4.79 | 12.44 | 4.94 | **4.54** |

One marginal transfer cell: **A5 at 90d** (joint geometry + lifecycle/turning
context) beats zero-change by ~5% on never-seen wheels (MAE 4.54 vs 4.79,
RMSE 8.98 vs 10.81, R² 0.28, Spearman 0.43, sign-acc 0.85). At 30/60d the
"gain" does not transfer, and in-cohort at 90d it does not hold either.

## 4. State-space sanity

`target = base + pred_dx` gives the same ordering (B0 1.59/1.73/2.89 < all arms).
Unsurprising — persistence dominates the ~1050 mm level; the whole question is
the ΔX margin, and it does not exist for diameter.

## Verdict (protocol step 12)

- Cross-dimensional root/flange geometry **contains genuine, transferable
  *directional* information about future diameter at longer horizons**
  (90d holdout Spearman 0.43, sign-acc 0.85, and an incremental ρ boost over
  dia-only even in-cohort). The user's latent-geometry intuition is *directionally
  correct*.
- But it does **not** reliably beat zero-change on future diameter: fails
  in-cohort at all horizons, fails on never-seen wheels at 30/60d, with only a
  single marginal 90d holdout win (~5% MAE).
- **Conclusion: `wsmDia` is not recoverable as an open-loop forecast target in
  the available data.** The latent/mixed-effects probe does not change the
  Phase 3F decision. Stop pursuing increasingly complex models (incl. LSTMs /
  deep sequence) for raw diameter.

## Residual

The 90d holdout A5 cell is the only evidence cross-dimensional geometry can
transfer to never-seen units. It is a diagnostic hypothesis, not a win:
recommend framing diameter as a **state-driven RUL/safety limit** (its real
monotone latent trajectory + root/flange/turning context), never an open-loop
forecast. If a *production* diameter model is ever required, it should be built
as a latent health-index model (joint dia+root+flange, documented turning/mount
boundaries) and validated on the 90d holdout A5 configuration — but per this
evidence the expected margin over persistence is ~0–5%, not a revolution.