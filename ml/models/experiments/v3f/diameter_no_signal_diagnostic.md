# Why `wsmDia` has no learnable degradation signal — diagnostic

**Status:** conclusive, closed
**Date:** 2026-08-11
**Substrate:** `model_datasets/v3f/change_space_benchmark.parquet` (239,684 rows, 16,050 wheelsets)
**Repro:** scripts in `C:\Users\CRIS\AppData\Local\Temp\opencode\*` (turning_pairs.py, turning_check2.py); findings below are numbers printed by those runs on the committed substrate + `model_datasets/v3/wheel_engineering_state_v1.0.parquet`.

## TL;DR

`wsmDia` (diameter) is not predictable in change space because the recorded ΔX is dominated by
**irreproducible variance that does not represent time-accumulating wear**:

- Same-interval (re)measurements < 1.5 days apart have a spread (std 9.19 mm) that is **99.8%**
  of the spread of all ΔX values across the whole dataset (9.20 mm).
- Signal-to-noise: 90-day median |ΔX| for diameter is ~1.5 mm versus a test–retest std of ~9.2 mm
  → SNR ≈ 0.16. `wsmRoot` (0.53) and `wsmFlangeThickness` (0.59) sit well above this floor.
- Within-wheel lag-1 rate autocorrelation is **negative**, not ~0: dia Spearman −0.11, root −0.42,
  flange −0.33 → past rate does not predict future rate; the more-negative (mean-reverting) the
  rate, the *better* the ML result (root/flange), reinforcing that what is being learned is a
  one-sided, consistent direction of travel, not a per-rate trajectory.

The "clean" signal magnitudes at 30–90 d (diameter median |ΔX| ~1.5 mm) are comparable to or below
the measurement/process noise floor. A model cannot beat zero-change when the target's own
irreproducible spread exceeds the signal it would need to reproduce.

## Evidence

### 1. Test–retest floor (short-interval pairs)
For consecutive measurements of the same wheelset separated by < 1.5 days (v3f substrate):

| dimension | std of ΔX <1.5 d | std of all ΔX | fraction of variance irreproducible |
|---|---|---|---|
| `wsmDia` | 9.19 | 9.20 | **0.998** |
| `wsmRoot` | —   | —   | ~0.86 |
| `wsmFlangeThickness` | — | — | ~0.94 |
| `wsmWheelGauge` | —   | —   | ~0.93 |

99.8% of the diameter change variance exists even when the two measurements are days apart on the
same wheel. That variance is not wear; it is measurement, recording, or process noise.

### 2. Noise floor from combined <20 d intervals (v3f)
Median short-horizon "degradation" is tiny compared to noise:

| dimension | MAE (<20 d, mm) | std (<20 d) | signal ≈ 90 d median |ΔX| ÷ noise std |
|---|---|---|---|---|
| `wsmDia` | 2.53 | 8.45 | ~0.16 |
| `wsmRoot` | —   | —   | ~0.53 |
| `wsmFlangeThickness` | — | — | ~0.59 |

### 3. Sign mixture
Measured on the v3f substrate (wsmDia ΔX):

| interval bucket | negative | positive | zero | median \|ΔX\| (mm) |
|---|---|---|---|---|
| < 1.5 d (same-day) | 0.294 | 0.082 | 0.625 | 0.0 |
| 30–90 d | 0.461 | 0.059 | 0.480 | 0.5 |
| 60–120 d | 0.557 | 0.066 | 0.376 | 1.5 |
| 90–180 d | 0.583 | 0.065 | 0.351 | 2.0 |
| 180–365 d | 0.588 | 0.073 | 0.339 | 2.695 |

If 90 d of diameter change were pure monotonic wear, ΔX should be ≈100% negative
at 60–120 d. It is only 56%: a third of pairs record zero change and ~7% record
**increases** — physically inconsistent with tread-wear-only (reprofiling removes
material; no process grows diameter on the same wheel). The huge zero mass is
quantization/reporting (0.010 mm nominal resolution but a 35–48% exact-zero
fraction), and the positive tail is measurement noise, not physical growth.
`wsmWheelGauge`: 90 d median |ΔX| ≈ 0.0; direction is essentially uninformative.

### 4. Ruling out turning/reprofiling contamination (the last suspect)
- WES `wsmturning1/2` flags 5,246 real reprofiling events; mean ΔX at turning ≈ **−5.02 mm**
  (median −5.0), 2.3% with |ΔX| > 20 mm.
- The ~2.3% large-positive rows (e.g. +68.7 mm on wheelset 30822) are **new-wheel mounts**
  (diameter 1018 → 1087 mm), not reprofiling — a second class of event inside the turning flag.
  Reprofiling cuts the tread, so it can only *decrease* diameter; only a mount increases it.
- **v3f already excludes these**: `turning_record_at_measurement` is all 0, `next/prev_turning`
  all 0, and only 32,540 rows carry a finite (mean 549 d old) `days_since_turning`. No v3f ΔX
  spans a turning row. So turning is **not** silently contaminating the diameter benchmark.
- Residual: 1,285 rows are post-turning within 30 d in v3f; their |ΔX| median (0.0) matches the
  normal population — no bump.

## Judgment

- The failure of `wsmDia` is a **data property**, not a modeling failure. The benchmark honestly
  reports zero-change as best for diameter; there is no ML fix for an irreproducible target.
- `wsmRoot` / `wsmFlangeThickness` carry a genuine, one-sided, transferable signal and are the
  dimensions worth forecasting; diameter should be treated as a context/safety limit (actionable
  RUL boundary) rather than a forecast target in open loop.

## Recommendations
1. **Feature (not target):** expose a `post_turning` / `days_since_turning` context feature and
   a `turning_side_disagreement` flag in the next substrate (v3g) so the reprofiling-mount
   distinction is explicit and learnable.
2. **Split events:** separate reprofiling (−Δ dia) from new-wheel mount (+Δ dia) in the WES
   lineage so future change models never fuse the two.
3. Target policy: forecast `wsmRoot`, `wsmFlangeThickness` in change space; use `wsmDia` only
   as a hard limit check (state-driven RUL), where its noise floor is tolerated.
4. Do not pursue a deep sequence model for `wsmDia`; the honest benchmark result (zero-change
   wins) is the correct engineering output.