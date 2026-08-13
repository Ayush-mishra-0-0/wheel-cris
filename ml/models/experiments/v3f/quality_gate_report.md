# Phase 3F — Quality Gate Report (Gate 3F-DQ)

**Date:** 2026-08-10 · **Status:** PASS with disclosures
**Substrate:** `model_datasets/v3f/change_space_benchmark.parquet` (v1.0.0)
**Experiment root:** `models/experiments/v3f/`

This report documents the Phase 3F change-space degradation-dynamics benchmark
per `docs/phase3f_plan.md`. Target is the **change** `dX = X_future − X_current`
per dimension (mm), so persistence = 0 and every model must earn its margin
against zero-change, population drift, and per-wheelset historical rate.

---

## 1. The decisive finding (frozen split, M4 vs zero-change MAE on ΔX)

| Dim | 30d | 60d | 90d | 180d | 365d | ΔX Spearman (90d) |
| --- | --- | --- | --- | --- | --- | --- |
| wsmDia (M4 / zero) | 2.15 / **1.59** | 2.23 / **1.73** | 3.25 / **2.89** | 4.52 / **4.06** | 6.47 / **6.13** | 0.17 |
| wsmFlangeThickness | 0.221 / **0.222** | **0.223** / 0.220 | **0.234** / 0.239 | **0.263** / 0.303 | **0.252** / 0.328 | 0.46 |
| wsmRoot | **0.557** / 0.542 | 0.625 / **0.593** | **0.746** / 0.776 | **0.773** / 0.959 | **0.850** / 1.051 | 0.45 |
| wsmWheelGauge | **0.124** / 0.069 | **0.127** / 0.070 | **0.163** / 0.090 | **0.106** / 0.057 | **0.121** / 0.051 | 0.17 |

**Honest headline:**
- **`wsmDia` (the headline dimension): no model beats zero-change.** The
  diameter trajectory contains essentially no predictable change at these
  horizons. Direction is right (sign acc ~0.83–0.88 on |ΔX|>1mm) but magnitude
  is noise.
- **`wsmFlangeThickness` and `wsmRoot` DO contain degradation dynamics:**
  M4 beats zero-change at 90/180/365d (and root at 365d by 19%), ΔX Spearman
  0.43–0.65, sign accuracy 0.65–0.84.
- **`wsmWheelGauge`: no learnable change** (M4 is consistently worse than
  zero).

This is exactly the persistence-dominance mechanism the plan predicted: on a
~1050 mm level a 0.5–1.4 mm 30–90d signal is invisible; in ΔX space it is the
entire target, and only the dims where real dynamics exist separate from zero.

---

## 2. Rolling production simulation — PRIMARY evidence (74 monthly refits)

Mean across refits (M4 vs zero-change MAE on ΔX):

| Dim | 30d | 60d | 90d | 180d | 365d | M4 rho 90d |
| --- | --- | --- | --- | --- | --- | --- |
| wsmDia | 6.84 / **5.23** | 6.34 / **5.65** | **6.95** / 7.39 | 8.24 / **6.97** | 12.0 / **8.33** | 0.35 |
| wsmFlangeThickness | **0.383** / 0.403 | **0.366** / 0.404 | **0.391** / 0.468 | **0.409** / 0.440 | 0.415 / **0.394** | 0.54 |
| wsmRoot | **0.919** / 1.120 | **0.931** / 1.245 | **0.978** / 1.510 | **1.071** / 1.438 | **1.041** / 1.154 | 0.64 |
| wsmWheelGauge | 0.191 / **0.133** | 0.171 / **0.129** | 0.163 / **0.115** | 0.181 / **0.131** | 0.164 / **0.074** | 0.26 |

**Rolling primary evidence:** `wsmRoot` beats zero-change at **every** horizon
consistently (rho 0.57–0.64, sign acc 0.72–0.78). `wsmFlangeThickness` beats
zero-change at 30–180d. `wsmDia` beats zero only at 90d; `wsmWheelGauge` never
does. The degradation-dynamics signal in the operating trajectory is real and
concentrated in **root radius and flange thickness**, not diameter.

---

## 3. Transferability stress — grouped-by-loco holdout (never-seen units)

Held-out units: 3,210 / 16,050 wheelsets; 5,026 held-out test rows.

| Dim | 30d M4/zero | 90d M4/zero | 180d M4/zero | rho 90d |
| --- | --- | --- | --- | --- |
| wsmDia | 2.01 / **1.48** | 3.09 / **2.68** | 3.98 / **3.51** | 0.18 |
| wsmFlangeThickness | **0.218** / 0.218 | **0.230** / 0.237 | **0.283** / 0.295 | 0.44 |
| wsmRoot | 0.578 / **0.553** | **0.741** / 0.751 | **0.778** / 0.837 | 0.42 |
| wsmWheelGauge | 0.128 / **0.069** | 0.157 / **0.090** | 0.099 / **0.048** | 0.19 |

The flange/root advantage **transfers to never-seen locomotives at 90–180d**
(consistent with the 3E forensic finding that operational context is
transferable). Diameter and gauge do not generalize; their M4 ΔX correlation is
~0.2 on unseen units. 365d holdout cells are n≈20 and undecidable.

---

## 4. Variance fidelity — the model still shrinks, but far less than Phase 3E

| Dim | varF 30d | varF 60d | varF 90d | varF 180d | varF 365d |
| --- | --- | --- | --- | --- | --- |
| wsmDia | 0.34 | 0.37 | 0.33 | 0.42 | 0.11 |
| wsmFlangeThickness | 0.56 | 0.59 | 0.59 | 0.66 | 0.77 |
| wsmRoot | 0.65 | 0.61 | 0.60 | 0.70 | 0.84 |
| wsmWheelGauge | 0.64 | 0.67 | 0.61 | 0.49 | 0.92 |

Phase 3E level-space predicted-ΔX std was ~0.34× observed. In change-space the
model is trained on ΔX directly and the shrinkage is much smaller (0.6–0.8× for
root/flange) but still present — magnitude is under-predicted, direction is
learned. **H4/H5 partially met: direction and magnitude ordering are learned;
spread is still too narrow for a calibrated engineering distribution.**

---

## 5. Horizon scaling (frozen split, mean |ΔX̂| vs mean |ΔX|)

| Dim | 30d pred/obs | 60d pred/obs | 90d pred/obs | 180d pred/obs | 365d pred/obs |
| --- | --- | --- | --- | --- | --- |
| wsmDia | 1.37/1.59 | 1.65/1.73 | 2.27/2.89 | 3.32/4.06 | 3.43/6.13 |
| wsmFlangeThickness | 0.15/0.22 | 0.15/0.22 | 0.15/0.24 | 0.21/0.30 | 0.27/0.33 |
| wsmRoot | 0.41/0.54 | 0.42/0.59 | 0.50/0.78 | 0.68/0.96 | 1.06/1.05 |
| wsmWheelGauge | 0.08/0.07 | 0.08/0.07 | 0.10/0.09 | 0.06/0.06 | 0.07/0.05 |

**H2 met for root** (predicted |ΔX| grows with H, tracks observed 30–180d,
lands on the 365d mark), **partially met for flange**, and **fails for diameter**
(predicted ΔX saturates ~3.4 while observed keeps growing to 6.1). The model
learns a *rate that scales with horizon* for the dims that carry dynamics, and
collapses on the dim that does not.

---

## 6. Exposure scaling (Spearman, distance-present subset)

| Dim | 30d pred/obs vs km | 90d pred/obs vs km | 90d pred/obs vs km/day |
| --- | --- | --- | --- |
| wsmDia | 0.08 / 0.12 | 0.04 / 0.01 | 0.02 / 0.04 |
| wsmFlangeThickness | −0.04 / −0.14 | −0.22 / −0.21 | −0.17 / −0.15 |
| wsmRoot | 0.09 / 0.26 | 0.22 / 0.38 | 0.12 / 0.22 |
| wsmWheelGauge | −0.01 / 0.01 | 0.10 / 0.05 | 0.04 / −0.01 |

**H3 partially met for root only:** predicted ΔX correlates with km in the
*same direction* as observed (0.22 vs 0.38 at 90d) but under-amplified.
Flange shows the observed negative correlation but under-scaled; diameter/gauge
show no exposure relationship at all. **Exposure (km) is not a strong driver of
predictable per-wheel change in this data** — consistent with the 3C Stage-D
distance ablation.

---

## 7. Conformal coverage on ΔX (empirical temporal, not a guarantee)

M4, frozen split, full_test:

| Dim | i80 30d | i80 90d | i95 30d | i95 90d |
| --- | --- | --- | --- | --- |
| wsmDia | 0.83 | 0.83 | 0.95 | 0.96 |
| wsmFlangeThickness | 0.85 | 0.86 | 0.97 | 0.97 |
| wsmRoot | 0.83 | 0.81 | 0.97 | 0.95 |
| wsmWheelGauge | 0.73 | 0.74 | 0.94 | 0.95 |

Intervals are now built on ΔX (the engineering quantity). Root/flange/dia are
near-nominal; **WheelGauge under-covers at i80 (0.73–0.74)** — the same
conditional-heteroscedasticity issue 3E found. Rolling-sim mean i80/i95 across
months is 0.78–0.81 / 0.94–0.95 for the dynamics dims.

---

## 8. Gate decision

| Gate | Requirement | Status |
| --- | --- | --- |
| 3F-A | v3f manifest SHA256; row identity; dX stats | PASS |
| 3F-B | baselines + M3/M4, all diagnostics, no tuning, labelled views | PASS |
| 3F-DQ | H1–H6 honestly tested and reported; variance/horizon/exposure shown | PASS |

**Answer to the Phase 3F question** ("does our data contain enough information
to forecast how much and in which direction a wheel changes over 30/60/90
days?"):
- **Yes for root radius and flange thickness** — direction (sign acc 0.7–0.84),
  ordering (ΔX Spearman 0.4–0.65), horizon scaling, and 90–180d transfer to
  never-seen units.
- **No for diameter and wheel gauge** — zero-change is the best forecast; the
  trajectory does not contain predictable diameter change at these horizons.

**Known limits:** (1) diameter is the dimension that dominates the engineering
level, and it is precisely the one with no learnable change; (2) magnitude is
still under-predicted (varF 0.6–0.8); (3) WheelGauge i80 under-coverage;
(4) 180d/365d holdout cells are small (n≈174/20); (5) exposure (km) explains
little of per-wheel change. No deep sequence model is introduced; no tuning was
performed; nothing was forced to beat persistence.
