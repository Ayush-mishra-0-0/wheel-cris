# Phase 5 — Layer 2 Degradation Benchmark Report

**Date:** 2026-08-13 · **Contract:** `wheel_profile_lifecycle_contract_v1` v1.2
**Substrate:** `model_datasets/v5/degradation_benchmark.parquet` (frozen)
**Runner:** `models/phase5/run_degradation_benchmark.py` → `degradation_benchmark.json`

## What was asked

Predict future **root / flange / tread wear** (and diameter) at 30/90/180 days
from a point-in-time anchor — Layer 2 of the Phase 5 plan, reusing the Phase 4
point-in-time machinery with the contract's post-turn eligibility rule
(anchor dropped if a turn/replacement occurs within 3d after it; within-segment
horizon target = last same-segment measurement in `(t, t+H]`).

## Verdict

**Yes — future wear is positively and stably forecastable at all three horizons,
and the gradient-boosting model (C1) beats persistence and linear extrapolation.
The naive per-day-slope extrapolation (B1) fails badly — honest negative result.**

## Static grid (temporal PIT test split; strict label-knowability at cutoff)

| dim @H | B0 persist MAE (R²) | B1 linear MAE (R²) | B2 ridge MAE (R²) | C1 XGB MAE (R²) | capture@5% |
| --- | ---: | ---: | ---: | ---: | ---: |
| root @30d | 0.715 (−0.38) | 1.51 (−31) | 0.706 (0.15) | **0.611 (0.31)** | 9.0% (vs 5% chance) |
| root @90d | 0.785 (−0.33) | 3.88 (−391) | 0.743 (0.08) | **0.673 (0.20)** | 7.9% |
| root @180d | 0.899 (−0.41) | 8.14 (−1731) | 0.791 (0.05) | **0.741 (0.15)** | 7.3% |
| flange @30d | 0.256 (−0.11) | 0.49 (−14) | 0.245 (0.24) | **0.219 (0.37)** | 9.6% |
| flange @90d | 0.270 (−0.12) | 1.17 (−201) | 0.258 (0.20) | **0.238 (0.29)** | 8.4% |
| flange @180d | 0.290 (−0.21) | 2.42 (−998) | 0.271 (0.13) | **0.255 (0.21)** | 7.8% |
| tread @30d | 0.593 (−0.04) | 1.51 (−36) | 0.643 (0.33) | **0.575 (0.40)** | 12.2% |
| tread @90d | 0.696 (−0.08) | 3.68 (−353) | 0.705 (0.27) | **0.652 (0.32)** | 10.6% |
| tread @180d | 0.831 (−0.18) | 7.74 (−1577) | 0.774 (0.21) | **0.720 (0.28)** | 9.2% |
| dia @30d | 2.04 (0.90) | 3.57 (0.33) | 3.37 (0.89) | 2.51 (0.91) | ≈ random |
| dia @90d | 2.92 (0.82) | 8.38 (−6) | 4.37 (0.79) | 3.50 (0.82) | ≈ random |
| dia @180d | 4.37 (0.70) | 17.3 (−37) | 6.70 (0.62) | 5.53 (0.69) | ≈ random |

## Rolling point-in-time (root/flange @90d, quarterly cutoffs — median ever cutoff)

| dim | B0 MAE med | B1 MAE med | B2 MAE med | C1 MAE med (IQR) | C1 R² med |
| --- | ---: | ---: | ---: | ---: | ---: |
| root | 0.798 | 3.78 | 0.721 | **0.505 (0.0067)** | **0.564** |
| flange | 0.283 | 1.05 | 0.262 | **0.195 (0.014)** | **0.532** |

Per-cutoff root 90d: MAE 0.512 / 0.499 / 0.505 → stable, no drift across
2025-11 → 2026-05. C1 trained PIT (label determinable at each cutoff) holds up.

## Interpretation

- **C1 > B2 > B0 > B1.** Random-walk persistence (B0) is a weak reference
  (negative R² on wear: test wear drifts from anchor), so positive R² and
  ~15–40% MAE cuts are real signal, not arbitrage.
- **B1 (per-day slope × H) explodes at 90/180d** (R² ≤ −30). Wear level is
  noise-dominated and mean-reverting between inspections; naive linear
  extrapolation is unusable — this is why Layer 2 uses learned degradation,
  and why the dashboard's wear bands must come from C1, never a hand formula.
- **capture@5% ≈ 1.5–2.4× random** on all three wear dims → the model genuinely
  ranks high-future-wear wheels to the top. This is the risk-ranking product
  that Layer 4 will consume.
- **Diameter is near-persistence**: B0 R² = 0.90. Not a learning problem —
  diameter only moves via machining (Layer 3), so within-segment dia prediction
  is bounded; use it as an ensemble constraint, not a headline.
- PR-AUC/ROC-AUC/Brier/ECE from the plan are **classification** metrics; they
  belong to Layer 4 (P(turn within H)) and Layer 3 (limit crossing), not to the
  level-regression targets here. capture@top-k is the layer-appropriate ranking
  metric and is reported.

## Feature footprint (frozen)

Base = v3f point-in-time machinery (state, km, RTIS coverage, root/dia rates) +
new Phase-5 features: within-segment horizon targets, post-turn eligibility
(2,354 transient anchors excluded, 0.98%), shed attribution (94.3% segments),
segment_index / n_prior_turns, and newly materialised point-in-time flange/thread
wear-slope columns (`ph5_wsmFlange/Thread_*`). 34 numeric + 4 categorical.

## Next (Layers 3–4)

- Layer 3: post-turn wear = f(pre-turn state, shed, profile class, position,
  loco type) → expected post-turn diameter = dia_before − cut (B−A model).
- Layer 4: P(turn within 30/90/180d) + limiting dimension (normalised
  margins from the §3 register), reporting the classification metrics the plan
  names against eligible rows.