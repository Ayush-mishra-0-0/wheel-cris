# Does averaging multiple observations reveal a stable diameter trajectory? — Phase 3F diagnostic

**Date:** 2026-08-11 · **Status:** descriptive trend YES, predictive trend NO
**Substrate:** `model_datasets/v3f/change_space_benchmark.parquet` + `model_datasets/v2/exposure_features_v2.parquet` + WES v1.0 (per-(wheel,`lifecycle_segment_id`) chronological series)
**Repro:** `C:\Users\CRIS\AppData\Local\Temp\opencode\dia_trajectory_smoothing.py`, `dia_trajectory_slopes.py`, `dia_trajectory_predict.py`, `dia_trajectory_horizon.py`

## Question

Does robust averaging / trajectory smoothing of multi-inspection diameter reveal
a stable degradation process that per-inspection ΔX hid behind measurement noise?
Tested separately for 2015–23, 2024, 2025–26.

## Answer

**Two-sided.**

1. **YES — the in-segment diameter trajectory is (likely) the most stable monotone
   signal of the four dimensions.** Theil–Sen slopes per (wheel, segment) are
   negative on **89–93 % of segments** (2015–23 89 %, 2024 93 %, 2025–26 80 %),
   and **69–73 % / 50 % of segments trend negative in *both* halves** (vs root
   6–12 % and flange 12–28 %). Averaging multiple observations removes most of
   the per-inspection spread: median |consec step| for dia collapses from
   ~0.9 mm (raw) to ~0.00 mm with a 3-median smoother (2015–23) and segment
   slope std falls ~⅓–⅔ in every era.

2. **NO — that stable trajectory does not forecast future cumulative diameter.**
   Every fixed-horizon forward test loses to the zero-change forecast:

   | era | horizon | n | MAE(zero-change) | MAE(trajectory-trend) | sign acc |
   |---|---|---|---|---|---|
   | 2015–23 | 30 d | 62,949 | 7.13 | 9.89 | 0.46 |
   | 2015–23 | 90 d | 58,457 | 9.95 | 13.34 | 0.55 |
   | 2024 | 30 d | 43,172 | 2.84 | 3.64 | 0.57 |
   | 2024 | 90 d | 39,368 | 4.85 | 5.33 | 0.75 |
   | 2025–26 | 30 d | 17,888 | 1.99 | 2.54 | 0.57 |
   | 2025–26 | 90 d | 14,582 | 3.66 | 4.23 | 0.68 |

   Fit-on-first-60%-predict-tail, part 2 results are the same: MAE(trend) is
   strictly worse than MAE(zero) in **all 9 era×dimension cells**.

So the latent trajectory exists (diameter declines monotonically within a
segment once you average out noise), but the historical slope does **not** carry
usable predictive information about the next 30/90 d of change. Why the trend
cannot be exploited:

- **Dense, burst-shaped segments.** Segments are dominated by same-day
  re-inspection bursts (median ~12 measurements within ≤1 day), so the fitted
  slope is mostly a *within-burst* quantity — it carries little time-translation.
- **Absorbed discrete jumps.** Segments still absorb undocumented events
  (turnings / wheel swaps not flagged as lifecycle boundaries). The forward
  tails are dominated by these: median |actual| tail change is 18.5 mm
  (2015–23), 10 mm (2024), 3.5 mm (2025–26) — an order above the smooth
  within-segment wear rate (−0.02 to −0.04 mm/day ⇒ −2 to −3.5 mm over 90 d).
- **Per-fit slope noise.** A mean-reverting measurement, once differenced, has
  lag-1 *negative* autocorrelation (−0.11 dia). The Theil–Sen slope over a short
  burst suppresses outliers but is still an estimate with large CI at the scale
  of the true signal.

## What this settles

- The user's reframing was right in one sense: **the raw pair ΔwsmDia is a
  terrible proxy** precisely because per-inspection noise hides a *real*,
  monotone, within-segment diameter decline — the dimension with the **most**
  consistent downward direction of all four.
- But after smoothing, **the trajectory is descriptive, not predictive.** No
  reasonable temporal smoothing or robust trend recovers a diameter forecast
  that beats zero-change at 30/90 d in any era, including 2024+ (where the
  noise floor halved).
- Conclusion stands, with a more precise wording:
  > WSM diameter is not usable as an open-loop **forecast** target in this data.
  > Its latent in-segment trajectory is real and monotone, so it remains valid
  > as a **safety/limit variable** (state-driven RUL check); the 
  > root/flange/geometry coupling and turning context remain the right place to
  > look for a *multivariate* recovery of a diameter signal (mixed-effects
  > latent model), not a univariate trajectory denoiser.

## Recommendations (updated)

1. Keep zero-change as the honest diameter benchmark; do not pursue univariate
   temporal smoothing/LSTM on raw dia.
2. The **mixed-effects / latent-state** route is still worth one experiment
   (per lit. the user linked): model `D` and `F` jointly with a latent wheel
   health factor and a per-segment random slope — but correct expectation is
   that it wins only if it exploits **cross-dimensional geometry
   (root+flange)** and **turning context**, since the dia-only trajectory has
   been shown to carry no predictive margin.
3. If modelling segments, split at **documented and undocumented turning/mount**
   events more aggressively (raw WES `wsmturning1/2` + jump guards), because
   absorbed discrete jumps are what defeat the trajectory forecast.