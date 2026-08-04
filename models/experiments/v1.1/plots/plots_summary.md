# V1.1 visualization suite — v1.0 vs v1.1 (same test split)

**Models compared:** released HGB regression baselines, both from `run_v1_1_baselines.py` on the
v1.1 dataset with the identical grouped-temporal split:

| model | experiment | features |
| --- | --- | --- |
| v1.0 | `models/experiments/v1.1/regression/experiment_0009` | 58 legacy X features |
| v1.1 | `models/experiments/v1.1/regression/experiment_0019` | 58 + 18 geom_* + 20 phys_* = 96 |

**Test set:** 28,066 intervals — identical rows in both models by construction.

## Headline numbers (test split)

| metric | v1.0 | v1.1 | change |
| --- | ---: | ---: | ---: |
| RMSE (mm) | 23.10 | 15.70 | **−32%** |
| MAE (mm) | 16.54 | 11.68 | **−29%** |
| R² | −0.086 | 0.498 | +0.58 |
| Spearman | 0.353 | 0.636 | +0.28 |
| predictions within ±10 mm | 41.6% | 52.5% | +10.9 pp |
| predictions within ±20 mm | 68.8% | 84.1% | +15.3 pp |
| worst-100 MAE | 117.5 | 66.6 | **−43%** |

---

## Figure-by-figure guide

### 01_predicted_vs_actual_scatter.png — **technical review**
Predicted vs actual next-interval diameter change on the delta scale, side-by-side, with the
y=x line and R²/RMSE/MAE annotated. The v1.1 cloud is visibly tighter around y=x. The
scatter uses the **delta** (change) axis because the raw diameter is dominated by wheelset
level — on a raw-diameter axis both models hug y=x and hide the improvement.

### 02_residual_distribution.png — **technical review**
Histogram + KDE of residuals. v1.1's distribution is narrower (σ lower) and more peaked at 0;
both are centered near zero (no bias shift), the win is variance reduction, not re-centering.

### 03_residual_vs_actual_diameter.png — **technical review**
Binned mean residual vs the actual next diameter. v1.0 shows systematic under/over-prediction
across the diameter range; v1.1's residuals hover near zero across the whole range — the
bias is largely removed.

### 04_residual_vs_current_diameter.png — **technical review**
Two panels vs the new `geom_wsmDia1` feature:
- *left:* mean residual (bias) vs current measured diameter — v1.1 flattens toward zero;
- *right:* MAE vs current diameter — the biggest improvement is on **worn wheels**
  (≤1040 mm, −65% MAE). This is the mechanism: v1.1 sees the wheel's current material state,
  v1.0 only saw interval *deltas*.

### 05_mae_rmse_by_diameter_band.png — **technical review**
Grouped bars of MAE and RMSE for current-diameter bands (>1080, 1060–1080, 1040–1060, <1040).

| band | n | MAE v1.0 | MAE v1.1 | change |
| --- | ---: | ---: | ---: | ---: |
| >1080 | 16,709 | 16.2 | 11.6 | −28% |
| 1060–1080 | 7,719 | 13.5 | 11.9 | −12% |
| 1040–1060 | 2,449 | 19.0 | 11.4 | −40% |
| <1040 | 1,189 | 36.2 | 12.6 | **−65%** |

The gain scales with wear — exactly what the physics features were designed to capture.

### 06_worst100_comparison.png — **executive + technical**
Worst-100 intervals (by |error|) per version. Left: scatter of each worst interval's error
under both models — only **14/100** overlap, and almost all points fall below the y=x line
(v1.1 error < v1.0 error). Right: worst-100 MAE drops from **117.5 → 66.6 mm (−43%)**.

### 07_error_by_shed.png — **executive**
Horizontal bar of MAE change by home shed (28 sheds, n≥50). Every shed improved; the
worst v1.0 shed (PADX, −55%) leaves the worst-100 entirely. One slide line: "every depot
got better, the weakest improved the most."

### 08_cumulative_error_ecdf.png — **executive**
ECDF of |error|. At any error budget, v1.1 covers a larger fraction of the fleet — e.g.
±20 mm covers 84% of intervals vs 69% for v1.0. Good for "what does this mean for
maintenance planning" conversations.

### 09_permutation_importance.png — **technical review**
Permutation importance (test, HGB v1.1), color-coded: physics (green), measured geometry
(blue), legacy (gray). `phys_remaining_material_mm_*` and `geom_wsmTireThikness*` dominate —
the answer to "why did it improve" in one chart.

### 10_ablation.png — **technical review**
Ablation (v1.0 / +geom / +phys / +all) for regression RMSE and large-loss PR-AUC.
`+geom` alone delivers nearly the full gain (RMSE 23.10 → 15.65; PR-AUC 0.845 → 0.928);
`+phys` alone is smaller; `+all` ≈ `+geom` (overlap ~1.0). Justifies the v1.1 feature set.

---

## How to present

- **Senior engineer (technical review):** 01, 02, 03, 04, 05, 09, 10 — these show the
  mechanism (current geometry), the ablation proof, and the feature attribution.
- **Management / decision (executive):** 06, 07, 08 — worst-case risk reduction, every
  depot improving, and the coverage ECDF.
- **One-liner for the deck:** "Same test set, zero new data sources: RMSE −32%, MAE −29%,
  worst-100 MAE −43%, and the improvement concentrates exactly where wheels are worn."

## Caveats

- R² in figure 01 is on the delta (interval change) axis; on raw diameter both models
  appear near-perfect and the comparison is invisible.
- v1.1 residual σ is reduced but the label still contains sentinel outliers (±1090 mm)
  that dominate worst-100; a quarantined label spec (v1.1) is a documented follow-up.
- Turning / survival tasks are **not** improved by geometry (PR-AUC ≈ prevalence,
  C-index ≈ 0.54) — those need V2.0 distance/track/telemetry data, not geometry.
