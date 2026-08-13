# ML Correctness Analysis — Diameter Forecast & Prediction Quality

> Scope: answer two questions from the Layer-5 review —
>   1. *Why does the model predict increasing wheel diameter?*
>   2. *Is the prediction actually good?*
> and define the fix list. Linked from `dashboard_roadmap.md` (P0).
>
> Sources: `ml/models/experiments/v5/degradation_benchmark.json`,
> `ml/models/experiments/v5/fleet_backtest.json`, `ml/models/phase5/dashboard/backend/features.py`,
> `ml/models/phase5/dashboard/backend/build_serving_models.py`, v2 label audit
> (`ml/models/experiments/v2/label_audit/`).
> Date: 2026-08-13

---

## 1. Why is the model predicting increasing diameter?

### 1.1 The physics

Within a lifecycle segment a wheel's diameter can only **decrease** (wear). Diameter
**increases** occur only when a wheel is **replaced** (a new/larger wheel is mounted). So an
"increasing diameter" forecast is physically invalid for a within-segment forecast.

### 1.2 What the benchmark shows

From `fleet_backtest.json` → `implausibility_diagnostics.wsmDia` (flag `increasing_diameter`,
predicted value > current + 0.001 mm):

| Horizon | actual_rate | model_rate |
| --- | --- | --- |
| 30d | 4.41% | 13.21% |
| 90d | 5.34% | 11.76% |
| 180d | 6.06% | 13.96% |

The model fires "increasing diameter" ~2–3× more often than it actually happens. (Note: the
*actual* rate is not zero — because the target can legitimately catch a post-replacement
measurement when a replacement boundary was missed, and because of measurement noise.)

### 1.3 Root causes (in order of likely contribution)

**A. Missed-replacement contamination of the target (data/leakage problem).**
The degradation target is "the last measurement in the same lifecycle segment within horizon H".
Segments are cut by the turn/replacement heuristic in `features.py:_boundaries`:
`turn_event` (turn flag + dia cut 1–25 mm + flange/root restore) **or** `replacement`
(`wsmProvDate` change OR wheel-age reset). When a replacement is missed by the heuristic,
a **post-replacement measurement with a larger diameter** is treated as a valid within-segment
target for a pre-replacement anchor → the training label itself says "diameter can rise".
The model then legitimately learns some increase signal, and it fires more often than the (also
contaminated) actual rate.

**B. Level-dominated regression (model problem).**
The serving models regress on absolute `mean_wsmDia` (~1090 mm with tiny true variation). R² for
dia is high (0.91 @30d, 0.82 @90d, 0.69 @180d) but this is almost entirely **between-wheel
level** variance, not trend. MAE is 2.5–5.5 mm while monthly wear is ~0.1–0.5 mm — the model
cannot resolve the trend; any slight level fluctuation or noisy covariate can tip a prediction
0.001+ mm above current.

**C. Signal below the repeatability floor.**
The v2 label audit (`repeatability_floor.json`) flags dia measurement noise; phase-3f
`dia_no_signal` diagnosis found noise-floor evidence for wsmDia trend. If within-segment dia
change is at/below the measurement repeatability floor, level regression on dia is not a sound
forecast target.

### 1.5 Evidence from the P0.2 audit (2026-08-13, `replacement_contamination_audit.py`)

The audit runs the **serving-exact** boundary logic (`features._boundaries`, which now delegates
to `build_lifecycle_segments.compute_boundaries`) over the full WES v3 (271,350 measurements,
19,167 wheelsets) and checks the v5 benchmark targets. Results written to
`ml/models/experiments/v5/replacement_contamination_audit.json`.

**Before the fix** (legacy `_boundaries` heuristic — dia up-jumps unflagged unless a turn/replacement
was otherwise detected):

| Measure | Result |
| --- | --- |
| Dia up-jumps ≥ 20 mm (consecutive measurements) | **7,928** total |
| … detected by turn/replacement boundary | 3,801 |
| … **missed by the boundary heuristic** | **4,127 (~52%)**, all within the same segment |
| Dia up-jumps ≥ 15 mm missed | 4,525 (52%) |
| Dia up-jumps ≥ 30 mm missed | 3,371 (51%) |
| Eligible wsmDia targets that RISE (> 0.05 mm) | 30d: 3.34% (4,156) · 90d: 3.67% (6,800) · 180d: 5.04% (11,065) |
| Median size of rising targets | 30d: +2 mm · 90d: +7 mm · 180d: **+26 mm** (p99 ≈ +70 mm) |
| Contaminated anchors enclosing a missed ≥ 15 mm jump | 30d: 18% · 90d: 42% · 180d: 71% |

Conclusion: **hypothesis A confirmed.** The boundary heuristic misses roughly half of all large
diameter up-jumps (real wheel replacements), leaving post-replacement (larger-diameter)
measurements inside a single segment. ~3–5% of dia training targets therefore encode "diameter
can rise", by tens of mm at 180d — exactly the signal the model reproduces as its ~12–14%
increasing-diameter forecast rate. The remaining contaminated anchors (small +1–2 mm rises)
are measurement noise / side-switching, a second (minor) upward-bias source.

**The fix** (`build_lifecycle_segments.py`): a same-wheelset consecutive `mean_wsmDia` up-jump
≥ `REPLACEMENT_DIA_JUMP_MM = 20.0` is a replacement candidate; it is **confirmed** when BOTH raw
sides (`wsmDia1` AND `wsmDia2`) rise ≥ the threshold **OR** the new level is sustained by the next
same-wheelset measurement within `REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM = 10.0`. Confirmed jumps are
flagged `replacement` and split the segment. This is now the single source of truth used by the
segment builder, the degradation substrate, and serving features. Validation
(`ml/models/validate_replacement_candidates.py`) quantified the 4,127 previously-missed ≥ 20 mm
jumps: median +48.5 mm (p10–p90 25–68 mm), 99.3% both-sides, 68% sustained; only 5 were noise.

**After the fix** (same audit, same WES v3):

| Measure | Before | After |
| --- | --- | --- |
| Replacement flags | 18,715 | **22,837** (+4,122) |
| Dia up-jumps ≥ 20 mm missed | 4,127 (52.1%) | **5 (0.06%)** |
| Dia up-jumps ≥ 30 mm missed | 3,371 (51%) | **1 (0.01%)** |
| Dia up-jumps ≥ 15 mm missed | 4,525 (52%) | 403 (4.66%) |
| Eligible wsmDia targets that RISE | 180d: 5.04% | **1.81%** (30d: 2.92% · 90d: 2.36%) |
| Median/p99 of rising targets (180d) | +26 mm / +70 mm | **+3.3 mm / +19.5 mm** |
| Contaminated anchors enclosing a missed jump | 180d: 71% | **14.9%** (30d: 3.7% · 90d: 6.7%) |

The residual contamination is small (median +1.5–3.3 mm, p99 ≈ 18–20 mm), consistent with
measurement noise / side-switching rather than full replacements. Segment count grew 39,971 →
**44,093** (+4,122), and the benchmark substrate was rebuilt on the clean boundaries.

### 1.4 Why the wear dimensions don't have the same problem

Flange/root/thread *grow* with wear and reset *down* at a turn, so "wear improving" is the
implausible direction. `fleet_backtest.json` shows the model over-predicts improvement too
(root 30d: actual 43.3% vs model 58.1%; thread 30d: actual 29.9% vs model 57.3%) — a milder,
related symptom of level-regression on noisy, weakly-trending targets.

---

## 2. Is the prediction even good?

### 2.1 Degradation (point forecasts, C1_xgb vs baselines)

Static PIT holdout (`degradation_benchmark.json`, post-fix substrate, **Δ-mode** — the model
regresses `Δ = tgt − anchor`; reported MAE/R² are reconstructed absolute levels so they are
comparable to the pre-fix run):

| Dim | Horizon | MAE (mm) | R² | Spearman | ΔMAE | ΔR² |
| --- | --- | --- | --- | --- | --- | --- |
| wsmFlange | 30d | 0.219 | 0.37 | 0.61 | 0.219 | 0.40 |
| wsmFlange | 90d | 0.237 | 0.30 | 0.56 | 0.237 | 0.36 |
| wsmFlange | 180d | 0.253 | 0.23 | 0.51 | 0.253 | 0.35 |
| wsmThread | 30d | 0.568 | 0.41 | 0.66 | 0.568 | 0.40 |
| wsmThread | 90d | 0.645 | 0.34 | 0.60 | 0.645 | 0.38 |
| wsmRoot | 30d | 0.597 | 0.31 | 0.58 | 0.597 | 0.44 |
| wsmRoot | 90d | 0.659 | 0.21 | 0.49 | 0.659 | 0.40 |
| wsmDia | 30d | 2.15 | 0.95 | 0.97 | 2.15 | 0.06 |
| wsmDia | 90d | 2.79 | 0.93 | 0.96 | 2.79 | −0.06 |
| wsmDia | 180d | 4.43 | 0.87 | 0.94 | 4.43 | −0.36 |

Notes on the Δ columns: ΔMAE equals level MAE by construction (level = anchor + Δ). ΔR² is the
R² of the model's *increment* vs the observed increment — for the wear dims the Δ signal is
genuinely predictable (0.35–0.44). For dia the ΔR² ≈ 0 (negative at 90d/180d): after removing the
anchor level, the remaining within-segment diameter change is small and noisy, so the level R²
(0.87–0.95) is driven by the anchor term. The value of the dia fix is not higher Δ-R² but the
collapse of the increasing-diameter implausibility (§2.1 below).

**Before → after (Δ-model on clean boundaries, C1_xgb static):**

| Dim | Horizon | MAE before→after | R² before→after |
| --- | --- | --- | --- |
| wsmRoot | 90d | 0.673 → 0.659 | 0.20 → 0.21 |
| wsmFlange | 90d | 0.238 → 0.237 | 0.29 → 0.30 |
| wsmDia | 30d | 2.51 → 2.15 (−14%) | 0.91 → 0.95 |
| wsmDia | 90d | 3.50 → 2.79 (−20%) | 0.82 → 0.93 |
| wsmDia | 180d | 5.53 → 4.43 (−20%) | 0.69 → **0.87** |

Interpretation:
- **Wear dims:** essentially unchanged (MAE ±2%, R² +2–8%), as expected — the fix only affects
  diameter segments. XGB beats persistence and ridge; R² ≈ 0.2–0.4 (decaying with horizon) and
  MAE is of the same order as typical monthly wear. Useful for **ranking** (Spearman 0.5–0.65)
  and for direction, **not** for precise absolute-level claims.
- **Dia:** the pre-fix R² was level-dominated and direction was wrong ~13% of the time (§1).
  On the clean boundaries, Δ-modeling cut dia MAE ~14–20% (largest at long horizons) and lifted
  R² to 0.87–0.95. The implausibility-bias check (`fleet_backtest.json`) collapsed: the
  increasing-diameter flag rate moved from +8.8pp above actual (30d) to +3.9pp, and 90d/180d went
  from +6.4/+7.9pp to **≈ 0 / −1.7pp**.
- **Rolling (recent cutoffs, retrained models)** is stronger: root median R² 0.56, flange 0.53 —
  retraining on the most recent data helps; the static holdout understates field performance.

### 2.2 Turning probability (P(turn), classification)

From `fleet_backtest.json` → `turn_probability`:

| Horizon | ROC-AUC | PR-AUC | Precision top-1% | Turns captured top-5% |
| --- | --- | --- | --- | --- |
| 30d | 0.885 | 0.114 | 0.190 | 50.8% |
| 60d | 0.906 | 0.187 | 0.300 | 55.0% |
| 90d | 0.906 | 0.255 | 0.385 | 53.8% |

(Recomputed on the post-fix lifecycle segments; C1_xgb. AUC improved ~+0.02–0.03 vs the pre-fix
run as the turn/replacement split is now cleaner.)

This is a genuinely useful **prioritisation/ranking** signal (AUC ≈ 0.89–0.91; ~51–55% of turns
in the top 5% of predicted risk). Strong shed heterogeneity exists (90d per-shed AUC 0.31–0.95),
so per-shed context matters. P(turn) is maintenance **behaviour**, not an engineering limit —
keep it separate from degradation state in the UI (see roadmap P2.2).

### 2.3 Verdict

| Claim | Status |
| --- | --- |
| "Rank wheelsets by wear/flange risk" | Supported (Spearman 0.5–0.65; P(turn) AUC 0.89+) |
| "Absolute RUL / precise future level (mm)" | Not yet — MAE ≈ wear magnitude; dia improved but still ±2–4 mm |
| "Diameter will increase" | Fixed — P0.2 (audit + Δ-model + clean boundaries); now ~flag-rate ≈ actual |

### 2.4 Trajectory-product analysis (flange/root/tread, `trajectory_product_analysis.py`)

Single artefact (`ml/models/experiments/v5/trajectory_product_analysis.json` +
`trajectory_residual_panel.png`) that makes the Δ-models honest for the
trajectory product. All numbers below are on the temporal test split.

**Delta metrics (C1_xgb; MAE is identical in both spaces by construction since
level = anchor + Δ; the difference is R²/ρ):**

| Dim | H | MAE (mm) | R² | ρ | ΔR² | Δρ |
| --- | --- | --- | --- | --- | --- | --- |
| wsmFlange | 30d | 0.219 | 0.37 | 0.61 | 0.40 | 0.57 |
| wsmFlange | 90d | 0.237 | 0.30 | 0.56 | 0.36 | 0.55 |
| wsmFlange | 180d | 0.253 | 0.23 | 0.51 | 0.35 | 0.58 |
| wsmRoot | 30d | 0.597 | 0.31 | 0.58 | 0.44 | 0.57 |
| wsmRoot | 90d | 0.659 | 0.21 | 0.49 | 0.40 | 0.59 |
| wsmRoot | 180d | 0.724 | 0.16 | 0.43 | 0.40 | 0.62 |
| wsmThread | 30d | 0.568 | 0.41 | 0.66 | 0.40 | 0.52 |
| wsmThread | 90d | 0.645 | 0.34 | 0.60 | 0.38 | 0.52 |
| wsmThread | 180d | 0.707 | 0.28 | 0.56 | 0.39 | 0.55 |

**Measurement-noise floor** (central same-timestamp, non-turn repeated readings of
the same wheelset; σ_single = std/√2): flange **0.114 mm**, root **0.105 mm**,
thread **0.066 mm**, dia 0.052 mm. These set the practical accuracy ceiling.

**Residual distribution** (realised − predicted change on test): flange RMSE
0.29–0.31 mm across horizons, root 0.75–0.91, thread 0.75–0.92. Model error is
≈3–14× the noise floor — i.e. still dominated by real (unexplained) change, not
measurement noise, so there is genuine headroom; only ~30–34% of residuals are
within the noise floor.

**Conformal intervals (80%, split-conformal on the Δ model, calibrated on the last
20% of train, coverage verified on test):**

| Dim | H | Width (±mm) | Empirical coverage |
| --- | --- | --- | --- |
| wsmFlange | 30/90/180 | 0.39 / 0.42 / 0.45 | 84% / 85% / 85% |
| wsmRoot | 30/90/180 | 1.01 / 1.14 / 1.22 | 82% / 83% / 82% |
| wsmThread | 30/90/180 | 0.88 / 1.05 / 1.14 | 77% / 80% / 80% |

Coverage is near the 80% target everywhere; flange/root run slightly wide
(conservative), thread is on target. Bands are decision-grade relative to action
thresholds only if the ±width is small vs the threshold gap — flange yes, root/
thread must be judged per threshold.

**Operational capture@k** (label = wheelset turned within H days; ranked by
predicted Δ; censored anchors dropped): at 90d, the top-10% predicted flange/root/
thread wear captures **58–93%** of wheelsets actually turned (thread 0.93, flange
0.84, root 0.58); at 180d top-10% captures 77–85%. 30d is unreliable (turn_rate
0.9%, capture@1% hits n<20 positives). This is the decision-aligned replacement
for capture@5% on continuous residual.

**Residual panels**: in-substrate loco 367 (6 wheelsets, 90d strip) and Loco 37597
via the serving feature path (6 wheelsets, 342 rows, 156 with realised targets) in
`trajectory_residual_panel.png`. 37597 flange strip RMSE ≈ in-substrate magnitude —
the serving path is trustworthy for out-of-substrate locos.

---

## 3. Improvement plan (tasks mirrored in `dashboard_roadmap.md` P0.2)

1. **Fix the target, not the output.**
   - ~~Audit missed replacements: scan every dia series for jumps > ~20 mm not flagged as
     turn/replacement; quantify contamination share in `degradation_benchmark.parquet`.~~
     **DONE** — `ml/models/replacement_contamination_audit.py` →
     `experiments/v5/replacement_contamination_audit.json` (see §1.5): ~52% of ≥20 mm dia
     up-jumps were missed; ~3–5% of dia targets encoded rises.
   - ~~Strengthen boundary detection: dia up-jump ≥ 20 mm (confirmed both-sides OR sustained)
     always cuts the segment; single config-registry rule, no duplicated thresholds.~~
     **DONE** — `compute_boundaries()` in `build_lifecycle_segments.py` is the single source of
     truth (`REPLACEMENT_DIA_JUMP_MM = 20.0`, `REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM = 10.0`);
     `features._boundaries` + `build_degradation_substrate.py` delegate to it. Missed ≥ 20 mm
     jumps: 4,127 (52%) → **5 (0.06%)**.
2. ~~**Model the delta.** Predict Δdim over H; serve `pred = anchor + Δ`. Removes level-dominance.~~
   **DONE** — benchmark, serving models, and fleet backtest run in Δ-mode (`TARGET_MODE="delta"`);
   MAE reconstructed as `anchor + Δ` for comparability (§2.1). Dia MAE −14…−20%, R² 0.69→0.87 @180d.
3. **Trajectory-product honesty layer** (see §2.4) — **DONE** through the serving/UI path:
   Δ-metrics exposed side-by-side, residual distribution + noise floor (flange 0.114 / root 0.105 /
   thread 0.066 mm), 80% conformal intervals with verified coverage (77–85%), operational capture@k
   (turn-within-H label), and residual panels incl. Loco 37597 via the serving path. The dashboard
   `/wheelset/{ws}/trajectory` contract now carries delta metrics, noise floor, conformal bands,
   realised residuals, physics flags and subgroup flags per forecast point (`trajectory_chart_v1`).
4. **Physics guard, reported not clipped.** If predicted dia > current + tolerance, emit the
   flag (backtest already does; fleet backtest wsmDia 90d/180d bias ≈ 0) and serve
   persistence/refusal with the flag + model version. **DONE at serving** — physics flags are
   attached per forecast in `predict_degradation` and the trajectory contract; reported, never clipped.
5. **Conformal intervals** (phase-3b machinery) — **DONE** in the trajectory artefact and attached
   to every flange/root/tread forecast point in the trajectory UI + replay backtest.
6. ~~**Re-baseline and record before/after** implausibility rates + MAE/R²/Spearman in this doc.~~
   **DONE** — see §1.5 (audit before/after) and §2.1 (Δ-model before/after).
7. ~~**Time-to-threshold / remaining-life view** (Tier 2): using Δ forecast + current value +
   action limits (condemning dia 1016 mm as hard stop) → expected days-to-limit with interval.~~
   **DONE (dia hard stop)** — serving-side piecewise-linear crossing of the 1016 mm condemning
   limit from the 30/90/180 Δ forecasts in `service._time_to_limit` (single source of truth).
   Exposed as `time_to_limit` per dim + `time_to_limit_summary` on the trajectory and replay
   contracts, with a days-to-condemning UI chip. **Limitations:** dia conformal bands are not yet
   calibrated (only point-path crossing reported for dia; interval edge fields present but null);
   flange/root/tread action limits remain pending engineering approval and are NOT reported.
8. ~~**Subgroup stability** (Tier 2): error + coverage by shed / profile / wheel position / age cohort /
   wear quantile.~~ **DONE** — `subgroup_stability.py` produces per-group bias/coverage and flags
   111 collapse rows (mostly shed × root/thread). Encoded as a **serving/UI confidence policy**
   (`development/dashboard/backend/subgroup_policy.py`): any wheelset whose shed / wear band /
   profile / position / age cohort is in `collapse_groups` for that dim×horizon gets a
   "reduced confidence" flag + amber treatment — point forecast shown but not decision-grade there.
   No model change; Tier-3 interaction work deferred until the policy is insufficient live.
9. **Reconsider the dia target**: prefer time-to-condemning-limit / rate features over level
   regression if noise floor persists. Dia is a derived diagnostic, not the product target.

---

## 4. Open questions / caveats

- **Distance gate ambiguity:** README says `interval_distance_km` is blocked, but the v5 substrate
  and `features.py` consume `distance_since_turning_km` / `km_last_{H}d` from exposure v2. Confirm
  whether the physical-distance release gate has been approved; if not, distance-derived features
  are a silent leak risk in the serving path.
- **Replacement truth is assumed, not source-authorised:** replacement detection is heuristic
  (`wsmProvDate` change / age reset). A source-authoritative replacement/repair record
  (engineering event ledger) is the correct long-term fix (see future_work.md §6).
- **Measurement noise floor:** confirm the repeatability floor for each dimension against the v2
  label audit before any absolute (mm) claim is shown to engineers.
