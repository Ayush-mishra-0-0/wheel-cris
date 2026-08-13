# M3-vs-M4 forensic / generalization study — Phase 3E

Status: **CONDITIONAL GO** (evidence of transferable operational value, with
explicit size, n, and coverage caveats). Diagnostic only; no causal claims; no
production horizon selected.

Results JSON: `models/experiments/v3e/forensics_m3m4.json`

## Protocol (fixed everywhere, nothing tuned)

- Rows/splits/seeds identical: chrono protocol = v3c frozen cohort (fit = first
  90% of train, cal = last 10%, eval = test rows); locohold = stress protocol of
  v3d (`~20%` of wheelset units held out, rng=SEED), eval on **test rows of
  never-seen units** — the transferability test.
- One XGB per (arm, dimension); hyperparameters fixed; all 5 bands.
- Arms: M3=M2+trajectory+distance history; M4=M3+operational group context
  (shed, wheel/axle position, defect zone/division, maintenance/RTIS counts);
  M4none=M4 **minus** the group-context family (counts only); M4id=M4 **plus**
  exact `wheelset_equipment_id` label.

## 1. M3 vs M4, chrono split

Mean MAE across the 4 dims (wsmDia/FlangeThickness/Root/WheelGauge), full_test:

| band   | M3     | M4     | delta  | key n |
|--------|--------|--------|--------|-------|
| 30d    | 0.7913 | 0.7617 | −0.030 | 9283  |
| 60d    | 0.8327 | 0.7939 | −0.039 | 6112  |
| 90d    | 1.1350 | 1.0898 | −0.045 | 8346  |
| 180d   | 1.3539 | 1.3134 | −0.041 | 828   |
| 365d   | 2.0949 | 1.8785 | −0.216 | 92    |

Dia alone: 2.257→2.147 (30d), 3.398→3.229 (90d), 6.988→6.306 (365d).
Every dimension improves except WheelGauge at short bands (M4 slightly worse:
0.117→0.123 at 30d; CI includes parity).

## 2. Loco-holdout (the key transferability test)

| band   | M3     | M4     | delta  | n     |
|--------|--------|--------|--------|-------|
| 30d    | 2.102  | 2.096  | −0.006 | 1887  |
| 60d    | 2.111  | 2.063  | −0.048 | 1259  |
| 90d    | 3.242  | 3.135  | −0.107 | 1686  |
| 180d   | 3.831  | 3.948  | +0.117 | 174   |
| 365d   | 11.676 | 10.818 | −0.858 | **20** |

(wsmDia; mean-diff pattern agrees on Flange/Root). **M4's advantage survives on
never-seen locomotives at 30–90d** — the operational context is transferable,
not memorized. 180d (n=174) and 365d (n=20) are too small to decide anything.

## 3. Is the gain memorization or context? (M4none / M4id)

- **M4none** (drop shed/position/defect, keep only counts) is **worse than M3**:
  30d Dia 2.435 vs M3 2.257 vs M4 2.147. Removing group context destroys the
  entire advantage; maintenance/RTIS counts alone add nothing.
- **M4id** (add exact wheelset identity) ≈ M4 (30d Dia 2.240; locohold 2.075)
  — adding identity gives **no extra transferable lift**, and under loco-holdout
  held-out units collapse to the `-1` identity code yet M4id still performs like
  M4. Conclusion: the M3→M4 gain is carried by **transferable group context
  (shed, position, defect family)**, not by counting activity and not by
  identity.

## 4. Permutation importance (M4, chrono, wsmDia)

Dominance: trajectory state variables (root/gauge changes & rates, ~12.6 MAE
spike when permuted). Operational context is a **marginal** contributor
(wheel_profile 0.44, wheel_position 0.41, wheel_age 0.41, RTIS counts ~0.40).
So operational context does not drive accuracy — it refines it at the tail,
which is exactly the transferable margin shown above.

## 5. Stratification (chrono, wsmDia)

- Loco-type stratification is **impossible** — `LocoType` has one value (WAP7).
- 18/26 sheds improved (LGDE −0.17, WATE −0.18, GDDE −0.25) but 8 sheds
  **worsened** (KYNE +0.25, ETE +0.16, PADX +0.14). Effect is
  **shed-heterogeneous**: do not assume a uniform benefit.
- Wheel position 1/11/9 and defect zones 3/10/11 show the largest, most-consistent
  gains; n≥7000 per position cluster (n≥50 for all strata shown).

## 6. n and uncertainty

- All 30–90d conclusions rest on n≥1,250 (locohold) / n≥6,100 (chrono).
- **180d (824/174) and 365d (92/20) are small; the ±4mm CI on 365d locohold
  means no claim can be made there.** Do not select these as horizon evidence.
- MAE se/95% CI reported per cell in the JSON.

## 7. Conformal recalibration (WheelGauge under-coverage)

Raw i80 empirical coverage for WheelGauge is 0.73–0.80 (under 0.80 nominal) and
is NOT fixed by a calibration-set multiplier search (mult ≈ 1.0 everywhere): the
width chosen from the calibration band already covers the calibration set, so a
scalar recalibration on cal rows is a no-op by construction. The under-coverage
reflects a test-cohort shift (conditional heteroscedasticity). **Action: widen
WheelGauge intervals or restrict to empirically-calibrated coverage; do not
quote 80% for it.** Other dims sit at 0.80–0.86 (nominal 80) across 30–90d.

## GO/NO-GO

**GO — conditional.**

Evidence: operational context is transferable (holds on never-seen units), not
identity-memorized, and not carried by maintenance counts. The architectural
step to a degradation/health-index model that consumes it is justified.

Conditions before treating this as final:
1. Keep the M4 context features; prefer M4 over M4id (no identity lift, leak
   risk for free).
2. Do not place weight on 180d/365d bands (n=174/20 in the holdout).
3. Report WheelGauge coverage honestly (or widen it); do not claim 80%.
4. Model shed as a explicit covariate (the benefit is shed-heterogeneous).
5. Loco-type remains untestable here (single WAP7) — keep in mind for any
   cross-type deployment claim.