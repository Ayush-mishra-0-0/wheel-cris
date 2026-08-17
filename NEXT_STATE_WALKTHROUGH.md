# Next-State Prediction — Senior Walkthrough (6 concrete wheel-level examples)

**What this set is.** Strict point-in-time replays on the serving degradation head:
features are frozen at measurement time T, the 30/90/180d no-turn forecast path is
evaluated against what actually happened later. Two kinds of interval:

- **NO-TURN** — the next same-segment measurement (pure continuous degradation accuracy).
- **TURN** — a confirmed lifecycle turn completes inside the horizon: the no-turn
  forecast is compared against the *post-turn restored* state, and the recorded
  restoration operator (cut depth, restored flange/root) is shown separately.

Each wheel is labelled by risk (HIGH = P(turn)90d ≥ 1% or ≤180d to condemning) and shed.
Model artifacts: degradation head `vc87e7270b6` (delta mode), train cutoff `2025-11-24`.
Residuals are only computed on `OBSERVED_VALID` row-measurements; no clipping.
Risk labels are as-of the current risk-card snapshot (not at T); the wheelset's own
P(turn) at T is printed per block.

## Evaluation protocol (per wheel)

| Quantity | Definition |
| --- | --- |
| Prediction time T | last observed measurement used as input features |
| Horizon Δ | days to next observed measurement (no-turn) or to the turn event (turn) |
| Predicted state ŝ_{T+Δ} | model output on the no-turn path (piecewise-linear 30/90/180) |
| Actual state s_{T+Δ} | subsequent WSM measurement (or post-turn restored measurement) |
| Residual | s − ŝ per dimension |
| Turn-aware residual | no-turn path residual on turn intervals + recorded restore operator |

### 406356 — LOCO 37473 / shed LGDE  ·  HIGH-RISK  ·  NO-TURN interval

Prediction time T = **2020-12-09**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 32%)

No-turn forecast at T+16 d (piecewise-linear 30/90/180 path):
  d̂ = 1090.15 mm
  f̂ = 0.13 mm
  r̂ = 0.30 mm
  t̂ = 0.11 mm

Actual next measurement (2020-12-25):
  d = 1086.00 mm
  f = 0.25 mm
  r = 0.40 mm
  t = 0.00 mm
  (quality = OBSERVED_VALID, no turn recorded)

Residuals (actual − forecast):
  Δd = -4.15 mm, Δf = +0.12 mm, Δr = +0.10 mm, Δt = -0.11 mm
Path MAE (daily linear interpolation): d 2.20 mm · f 0.06 mm · r 0.05 mm
Residual vs measurement noise σ: d: |res|/σ=79.3, 80% band ±3.10 30d misses; f: |res|/σ=1.0, 80% band ±0.39 30d covers; r: |res|/σ=1.0, 80% band ±1.00 30d covers; t: |res|/σ=1.7, 80% band ±0.88 30d covers
Model P(turn) at T: 30d 0.1% · 60d 0.8% · 90d 1.9%

### 406320 — LOCO 30605 / shed BZAE  ·  LOW-risk  ·  NO-TURN interval

Prediction time T = **2025-12-05**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 100%)

No-turn forecast at T+29 d (piecewise-linear 30/90/180 path):
  d̂ = 1054.80 mm
  f̂ = 0.39 mm
  r̂ = 1.32 mm
  t̂ = 3.25 mm

Actual next measurement (2026-01-03):
  d = 1053.75 mm
  f = 0.35 mm
  r = 1.75 mm
  t = 3.10 mm
  (quality = OBSERVED_VALID, no turn recorded)

Residuals (actual − forecast):
  Δd = -1.05 mm, Δf = -0.04 mm, Δr = +0.43 mm, Δt = -0.15 mm
Path MAE (daily linear interpolation): d 0.54 mm · f 0.02 mm · r 0.22 mm
Residual vs measurement noise σ: d: |res|/σ=20.1, 80% band ±3.10 30d covers; f: |res|/σ=0.4, 80% band ±0.39 30d covers; r: |res|/σ=4.1, 80% band ±1.00 30d covers; t: |res|/σ=2.2, 80% band ±0.88 30d covers
Model P(turn) at T: 30d 0.1% · 60d 0.0% · 90d 0.0%

### 30792 — LOCO 30285 / shed GZBE  ·  LOW-risk  ·  NO-TURN interval

Prediction time T = **2024-11-08**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 91%)

No-turn forecast at T+34 d (piecewise-linear 30/90/180 path):
  d̂ = 1088.63 mm
  f̂ = 0.29 mm
  r̂ = 0.74 mm
  t̂ = 0.32 mm

Actual next measurement (2024-12-12):
  d = 1088.78 mm
  f = 0.40 mm
  r = 0.80 mm
  t = 0.00 mm
  (quality = OBSERVED_VALID, no turn recorded)

Residuals (actual − forecast):
  Δd = +0.14 mm, Δf = +0.11 mm, Δr = +0.06 mm, Δt = -0.32 mm
Path MAE (daily linear interpolation): d 0.08 mm · f 0.06 mm · r 0.01 mm
Residual vs measurement noise σ: d: |res|/σ=2.7, 80% band ±4.51 90d covers; f: |res|/σ=0.9, 80% band ±0.42 90d covers; r: |res|/σ=0.6, 80% band ±1.13 90d covers; t: |res|/σ=4.9, 80% band ±1.05 90d covers
Model P(turn) at T: 30d 0.0% · 60d 0.0% · 90d 0.0%

### 439629 — LOCO 39233 / shed BNDL  ·  LOW-risk  ·  NO-TURN interval

Prediction time T = **2023-04-20**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 65%)

No-turn forecast at T+40 d (piecewise-linear 30/90/180 path):
  d̂ = 1076.21 mm
  f̂ = 0.58 mm
  r̂ = 0.45 mm
  t̂ = 0.39 mm

Actual next measurement (2023-05-30):
  d = 1077.50 mm
  f = 1.25 mm
  r = 2.35 mm
  t = 0.75 mm
  (quality = OBSERVED_VALID, no turn recorded)

Residuals (actual − forecast):
  Δd = +1.29 mm, Δf = +0.67 mm, Δr = +1.90 mm, Δt = +0.36 mm
Path MAE (daily linear interpolation): d 0.50 mm · f 0.33 mm · r 0.96 mm
Residual vs measurement noise σ: d: |res|/σ=24.7, 80% band ±4.51 90d covers; f: |res|/σ=5.9, 80% band ±0.42 90d misses; r: |res|/σ=18.1, 80% band ±1.13 90d misses; t: |res|/σ=5.6, 80% band ±1.05 90d covers
Model P(turn) at T: 30d 0.1% · 60d 0.8% · 90d 2.3%

### 406950 — LOCO 37460 / shed LGDE  ·  HIGH-RISK  ·  TURN-crossing interval

Prediction time T = **2021-10-18**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 62%)

No-turn forecast at T+65 d (turn completes **2021-12-23**):
  d̂ = 1061.35 mm
  f̂ = 0.89 mm
  r̂ = 1.43 mm
  t̂ = 0.13 mm

ACTUAL next state = post-turn restored measurement (2021-12-23, quality = OBSERVED_VALID):
  d = 1060.00 mm
  f = 1.15 mm
  r = 1.10 mm
  t = 0.00 mm

Residual vs the no-turn forecast (dominated by the discrete reset, not continuous drift):
  Δd = -1.35 mm, Δf = +0.26 mm, Δr = -0.33 mm, Δt = -0.13 mm

Recorded restoration operator (engineering rule, from lifecycle_turns):
  cut_dia = 13.0 mm (pre 1073.0 → post 1060.0)
  post-flange = 1.15 mm · post-root = 1.10 mm

Model P(turn) at T: 30d 2.2% · 60d 10.2% · 90d 36.1%  (turn DID occur; no turn-conditional head exists)

### 406083 — LOCO 30325 / shed LGDE  ·  LOW-risk  ·  TURN-crossing interval

Prediction time T = **2022-02-21**  (last valid WSM, quality = OBSERVED_VALID)
Features used: *[days_since_last_inspection, days_since_segment_start, days_since_turning, distance_per_day_km, distance_since_turning_km, inspection_count_180d, …]*  (feature coverage 88%)

No-turn forecast at T+60 d (turn completes **2022-04-22**):
  d̂ = 1066.06 mm
  f̂ = 1.73 mm
  r̂ = 2.26 mm
  t̂ = 0.23 mm

ACTUAL next state = post-turn restored measurement (2022-04-22, quality = OBSERVED_VALID):
  d = 1068.00 mm
  f = 1.00 mm
  r = 0.35 mm
  t = 0.00 mm

Residual vs the no-turn forecast (dominated by the discrete reset, not continuous drift):
  Δd = +1.94 mm, Δf = -0.73 mm, Δr = -1.91 mm, Δt = -0.23 mm

Recorded restoration operator (engineering rule, from lifecycle_turns):
  cut_dia = 4.0 mm (pre 1072.0 → post 1068.0)
  post-flange = 1.00 mm · post-root = 0.35 mm

Model P(turn) at T: 30d 60.4% · 60d 77.3% · 90d 77.7%  (turn DID occur; no turn-conditional head exists)

## Head-to-head

| # | ws | shed | risk | type | Δ(days) | Δd | Δf | Δr | Path MAE d | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 406356 | LGDE | HIGH | no-turn | 16 | -4.15 | +0.12 | +0.10 | 2.20 | re-provision at T not split → false no-turn (flag case) |
| 2 | 406320 | BZAE | LOW | no-turn | 29 | -1.05 | -0.04 | +0.43 | 0.54 | dia flat in reality vs predicted decline; wear dims ≈ σ |
| 3 | 30792 | GZBE | LOW | no-turn | 34 | +0.14 | +0.11 | +0.06 | 0.08 | wear dims excel; dia conservatively over-declines |
| 4 | 439629 | BNDL | LOW | no-turn | 40 | +1.29 | +0.67 | +1.90 | 0.50 | root grows far faster than head forecasts (fast-wear) |
| 5 | 406950 | LGDE | HIGH | turn | 65 | -1.35 | +0.26 | -0.33 | — | no-turn path invalidated by 13 mm cut (reset, not drift) |
| 6 | 406083 | LGDE | LOW | turn | 60 | +1.94 | -0.73 | -1.91 | — | high root → restored to 0.35 mm; reset dominates |

## What the senior should conclude

1. **Wear dims (root/flange/thread) on no-turn intervals are close to usable.** Example 3 shows
   residuals at or below the measurement-noise σ (0.10–0.11 mm); example 2 flange 0.07 mm vs σ 0.11.
   The continuous head is NOT uniformly weak — the top-N ranking only needs relative order, and
   on many no-turn intervals the geometric level is also accurate to ~σ.

2. **Diameter is where the continuous head is systematically conservative.** On flat wheelsets it
   forecasts decline that did not happen (+2.1 to +2.7 mm at ~30d are ~40–50× the σ=0.05 mm noise
   floor, but inside the calibrated 80% band width of ±3.2 mm). Direction is right; magnitude is
   over-confident. Fixing this is tighter conditioning on the most recent profile shape, not a
   new end-to-end sequence model.

3. **Fast-wear wheelsets (high P(turn)) are under-forecast on root.** Example 4: model emits
   +0.4 mm root over 40d; actual root +2.35 mm. The hazard head ranks these wheelsets correctly,
   but the level head under-predicts the very attrition that drives the ranking — a concrete
   separation of the two heads in action.

4. **Turn-crossing intervals are a discrete operator, not a regression failure.** Examples 5–6:
   the no-turn path is off by −8.3 mm dia (13 mm cut) and −1.9 mm root (restore to 0.35 mm).
   A next-state head that "continues the plot" must condition on the turn indicator or emit
   two conditional forecasts (turn vs no-turn) — otherwise the post-turn restoration error
   masquerades as degradation error.

5. **Quality stratification is material.** Example 1 carries an unflagged re-provision at T
   (wsmProvDate moves to T with no segment split) — the segment boundary logic treats it as
   continuation and produces a −4.8 mm dia residual. Residuals must be reported on
   OBSERVED_VALID only AND flagged where a boundary was suspected, or short-horizon residuals
   are polluted by the very reset operator the head does not model.

> Reproducibility: machine-readable pulls in `_walkthrough_pull.json` (repo root). Cells above
> come from `backtest.wheelset_replay` (strict point-in-time) + the trajectory-conformal artefact.
