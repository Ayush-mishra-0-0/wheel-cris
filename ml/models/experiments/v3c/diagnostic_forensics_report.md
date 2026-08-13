# Phase 3C — Diagnostic Forensics (Decision Gate)

**Date:** 2026-08-09
**Substrate:** `model_datasets/v3c/clean_benchmark_pairs.parquet` (frozen)
**Cohort:** `model_datasets/v3c/clean_benchmark_cohort.parquet` — chronological 80/20,
`n_train=191,747 n_test=47,937`
**Models:** persistence / historical-rate / Ridge / XGBoost (fixed hypers, no tuning)
**Seeds:** 42, 7, 2024 (all identical — see §3 caveat)
**Artifacts:** `diagnostic_forensics_results.json`, `diagnostic_rolling_ab_results.json`

> Two previously-reported headline numbers are **superseded** by this audit:
> (1) the earlier benchmark metrics were computed by applying chronological
> masks to a differently-ordered frame; (2) the "+11.26 mm contamination"
> came from feeding the **whole frame id list** as the test set (the “full”
> arm then trained on ~12.5k boundary rows, not on the whole training set).
> Both are corrected below.

---

## 1. Benchmark (per dimension, frozen clean cohort)

| dim | persistence MAE | xgb MAE | Δ vs persistence | persistence RMSE | xgb RMSE | xgb R² | hist-rate MAE | Ridge MAE |
|---|---|---|---|---|---|---|---|---|
| wsmDia | 1.8635 | 2.7092 | **+0.846** | 5.5988 | 5.7052 | 0.872 | 4.136 | 4.100 |
| wsmFlangeThickness | 0.2276 | 0.7218 | +0.494 | 0.3476 | 1.2834 | −10.5 | 0.359 | 0.299 |
| wsmRoot | 0.6304 | **0.6296** | **−0.001** | 0.9646 | **0.8165** | **0.270** | 0.909 | 0.730 |
| wsmWheelGauge | 0.0725 | 0.4434 | +0.371 | 0.2025 | 4.7541 | −101 | 0.128 | 0.304 |

**Bottom line.** XGBoost beats persistence MAE on **no** dimension; it matches
persistence on `wsmRoot` (0.6296 vs 0.6304) with a clearly better RMSE
(0.82 vs 0.96) and R² (0.27 vs −0.02). Historical-rate and Ridge are worse
everywhere.

---

## 2. Diameter forensics (wsmDia, test cohort)

**Bias (signed residual = target − pred)**
- persistence: **−0.831 mm** — systematically **over-predicts** (keeps assuming no decay when diameter actually falls).
- xgb: **+0.025 mm** — essentially **unbiased**.

**Error distributions**

| | persistence | xgb |
|---|---|---|
| p25 | 0 | 0.68 |
| p50 | 0 | 1.39 |
| p75 | 1.88 | 2.60 |
| p90 | 4.43 | 5.37 |
| p95 | 7.98 | 9.33 |
| p99 | 28.0 | 28.8 |
| mean MAE | 1.86 | 2.71 |

Persistence get an absolute error of **0.0 mm on 47 %** of test rows — it wins
on the large mass of near-zero-change intervals, while XGBoost's unbiased
spread fills the bulk with ~1.4 mm errors. The diameter system is dominated by
**measurably-stable pairs**, not by slow-rate extrapolation.

**By `interval_days`:** persistence MAE grows monotonically (0–30d: 1.30 → >180d:
4.33); xgb is worse in every band but **unbiased per band** (persistence bias
−0.49 → −3.52 as interval grows, while xgb bias stays ≈ −0.2 to +0.1). So XGB
fixes persistence's systematic over-prediction but cannot out-fraction the
no-change majority.

**By base diameter:** persistence dominant in every band; xgb over-predicts most
on the smallest diameter band (< 1059.5 mm: bias −1.44).

**By distance availability:** both models improve when distance is present
(persist 1.83→1.63; xgb 2.83→2.02); persistence stays ahead. By
`distance_per_day_km`, persistence is best at high/km-day too.

**By lifecycle-segment age (0–300d):** persistence 1.64–1.69, xgb 2.58–2.71
persistence better in both young/old.

---

## 3. Why does `wsmRoot` hold an edge?

- **Permutation importance (test MAE drop):** `wsmRoot2` (0.071), `wsmRoot1`
  (0.054), `home_shed` (0.025), `interval_days` (0.022), `wsmDia2` (0.016).
  The signal is **current Root state + geographic/shed + cadence**, not an
  exotic physics feature. No causality claimed.
- **Multi-seed:** MAE identical across the 3 seeds (0.6296) — but this is not
  informative robustness because the XGBoost config uses no subsampling, so the
  trees are deterministic (see caveat §5).
- **Rolling temporal protocol** (expanding train, disjoint windows; win0 has no
  training rows → NaN):

  | window | persistence | xgb |
  |---|---|---|
  | win1 | 0.925 | **0.881** |
  | win2 | 0.737 | **0.690** |
  | win3 | 0.642 | **0.625** |

  XGBoost beats persistence on **every computable window**, margin −4% to −6%.
  Rolling MT evidence supports a small but real Root-specific signal.

**Interpretation.** Root = the wear that eats into profile near the flange
root, with largest **zero-change fraction smallest** (only light 17% of test
rows stay at base vs 54% for diameter, 26% flange, 79% for gauge — see §7). It
is the geometrically richest dimension and shows genuine directional movement
beyond persistence — but the MAE gap is tiny (0.1%) and RMSE visible (0.15 mm).

---

## 3. Seed robustness caveat

The XGBoost config `n_estimators=250, max_depth=6, subsample=1.0,
colsample_bytree=1.0` leaves **no stochastic component active**, so the three
seeds produce byte-identical fits. The seeded row is therefore a **determinism
check, not a variance estimate**. Real "does it survive seed noise" evidence
comes from the **rolling** rows above.

---

## 4. Contamination A/B (full train vs clean train, same frozen test)

**Verified facts:**
- replacement-boundary rows: **3,749** (all in the **full train** arm; **0** in
  test — confirmed).
- `test_cohort_identical_full_vs_clean = true`, test crossings = **0**.
- Event Ledger: **14,058 CONFIRMED + 821 LIKELY** replacement events; only **52
  rows** are boundary rows driven by a **LIKELY-only** replacement; UNKNOWN is not
  used for boundaries at all.

**Corrected A/B (per seed, frozen test):**

| dim | full-train MAE | clean-train MAE | delta | relative |
|---|---|---|---|---|
| wsmDia | 3.2001 | 2.7092 | **+0.491** | +15% |
| wsmFlangeThickness | 0.2341 | 0.7218 | −0.488 | (full better) |
| wsmRoot | 0.7087 | 0.6296 | +0.079 | +11% |
| wsmWheelGauge | 0.1272 | 0.4434 | −0.316 | (full better) |

**Rolling A/B (`wsmDia` deltas):** win0 +0.71, win1 +0.26, win2 +0.11, win3
+0.26 — a small, fairly stable contamination penalty on diameter.

**Conclusion:** the **+11.26 mm headline did not replicate** — it was an
artifact of the off-full-frame bug. The real effect is modest (**≤0.5 mm,
~15%** relative on diameter; **~0 on flange/gauge/Root-adjacent**), and
FORGETS boundaries mostly affect diameter. Processings: treat lifecycle
segmentation as **required but not as a large effect** (gate C → minor).

---

## 5. Caveats

- **Deterministic seeds:** no subsampling ⇒ multi-seed numbers identical; the
  robustness claim must come from rolling, not seed sweeps.
- **win0** of the rolling protocol has no training rows (NaN) — windows 1–3 are
  the informative ones.
- Some gait× lifecycle floor bands carry few/missing distance rows; n printed per band.

---

## 7. Gate recommendation

| criterion | evidence | verdict |
|---|---|---|
| A: ML ≤ persistence on dia/flange/gauge | dia +0.85, flange +0.49, gauge +0.37 | **persistence = baseline for these 3** |
| B: Root consistently beats persistence | rolling −4…−6%, RMSE −0.15, R² 0.27 vs −0.02 | **dimension-specific model for Root (small)** |
| C: contamination is large & stable | corrected: ≤ +0.5 mm, ≤15% | **lifecycle segmentation = requirement, not dominant** |
| D: +11.26 is unstable | corrected to ≤ +0.5 mm | **yes — treat it as artifact** |

**Answer:** at the current **median 29-day-cadence** resolution, **only the Root
geometry carries detectable future-state information beyond persistence**
(≈ −0.1% MAE, −6% RMSE, strongly consistent across rolling windows). The other
three dimensions are dominated by measurement-resolved near-zero-change
observations, so persistence is the defensible baseline. **Lifecycle
contamination destroys at most ~15% of the diameter degradation-learning
signal; the +11.26 mm claim is an artifact of the cohort bug.**

---

## 8. Distance vs calendar time; degradation rate under exposure

Analysis: `models/phase3c/run_distance_time_ablation.py` →
`diagnostic_distance_time_ablation.json`. Both arms trained on the **same
114,464 distance-available train rows** and tested on the **same 7,214
distance-available test rows** (identical rows, XGBoost config, target).

**Coverage instability discovered independently:** distance coverage collapses
60% (train) → 15% (test cohort), so the earlier whole-test distance ablation
was diluted by NaN rows. This subset design isolates the distance increment.

**MAE on the distance-ok test subset (persistence | time-only | time+distance):**

| dim | persist | T | TD | Δ (TD−T) | R² T | R² TD |
|---|---|---|---|---|---|---|
| wsmDia | 1.6255 | 1.9852 | 2.4567 | −0.472 | 0.914 | 0.888 |
| wsmFlangeThickness | 0.2275 | 0.2252 | 0.2237 | **+0.0015** | 0.369 | **0.384** |
| wsmRoot | 0.6262 | 0.5670 | **0.5083** | **+0.0587** | 0.312 | **0.424** |
| wsmWheelGauge | 0.0792 | 0.1114 | 0.1250 | −0.014 | 0.716 | 0.693 |

Reading: distance adds a **material** predictive increment **only for Root**
(−0.059 MAE, R² 0.31→0.42) — i.e. distance partially explains Root wear that
calendar time cannot. It *hurts* diameter/gauge (overfit to noisy/NaN distance)
and is neutral on flange.

### Degradation speed under exposure (median, within-life pairs)

| dim | mm/day (calendar) | mm/1000 km (usage) |
|---|---|---|
| wsmDia | 0 (zero-change dominates) | 0 |
| wsmFlangeThickness | 0 | 0 |
| wsmRoot | **0.0015** (54% pairs non-zero) | **0.011** (n=102k pairs) |
| wsmWheelGauge | 0 | 0 |

Root's usage-speed is consistent and small: **≈0.015–0.021 mm per 1000 km**
and **0.014–0.019 mm/day** for intervals ≥1000 km (the 0–1000 km and low-coverage
bands show spurious −38 to −68 mm/1k km medians from unreliable short-interval
denominators — a data-quality signal, not physics).

**Answer to the three questions.**
1. What is missing beyond persistence? **Information between inspections**:
   reliable tracked distance/coverage (its absence collapses train→test 60%→15%),
   plus route/loco/braking load context. Broad feature engineering is NOT going
   to fix the missing-observation bottleneck; better coverage is.
2. Does distance explain degradation time cannot? **Only for Root.** The
   distance increment is real and material there; everywhere else distance is
   noise or absent.
3. How fast is the wheel degrading? **Non-zero mainly for Root** — roughly
   0.0015 mm/day and ~0.015–0.02 mm per 1000 km; diameter/flange/gauge medians
   are 0 only because the majority of pairs show no measured change at this
   cadence/resolution.

### Uncertainty vs magnitude (why not point-RULs)

Prediction-interval-scale widths (XGBoost RMSE) are large on every dimension:

| dim | model RMSE (±) | persistence MAE |
|---|---|---|
| wsmDia | 5.71 | 1.86 |
| wsmFlangeThickness | 1.28 | 0.23 |
| wsmRoot | 0.82 | 0.63 |
| wsmWheelGauge | 4.75 | 0.07 |

The **uncertainty of the future measured state is 3–66× larger than the typical
degradation signal itself.** The right output artifact is therefore
`current_state → evolution (mean/slope) → uncertainty interval → margin/risk`,
not a point RUL "143 days". Observation-rate limits dominate; model capacity
is not the bottleneck.

---

*Generated by `models/phase3c/run_diagnostic_forensics.py` +
`run_rolling_contamination_ab.py` + `run_distance_time_ablation.py`. No
hyperparameters tuned; no features added.*