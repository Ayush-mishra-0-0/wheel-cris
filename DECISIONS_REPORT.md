# Decision Report — Railway Wheel Engineering Intelligence Platform

> Consolidated, source-referenced record of the engineering and product decisions made
> across this project: **data segments**, **model training**, and **everything else**
> (product framing, validation, serving, UI, integration).
>
> This is a living index — the primary source of truth is always the referenced files.
> Last compiled: 2026-08-19. Where a number changed between versions, both are given with
> context so the report does not misrepresent either build.
>
> **2026-08-19 — Limit register locked (Wrpld):** flange 3.0 / root 6.0 / tread 6.5 mm are
> APPROVED via the Wrpld table (`ml/configs/limit_register_v1.json`). The earlier "root 3 mm"
> figure (degradation_semantics Q8) is superseded; the Phase 4 root-constraint target is
> retuned to `root > 6 mm` (risk_event_contract v1.1).

---

## 1. Executive summary — decisions at a glance

| Area | Headline decision |
| --- | --- |
| Product | Engineer-facing product is the **flange / root / tread trajectory** (30/90/180 d) with confidence + residual evidence + time-to-action; **diameter is a derived diagnostic**, **P(turn) is a prioritisation launcher**, never the ranking's sole signal |
| Problem framing | Three connected questions (current health → why → RUL); outputs are **"likely contributing factors"**, never causal claims |
| Cohort | **WAP7** only, resolved by name via `LocoTypes` lookup → **2,317 locos**, 19,167 wheelsets, 271,350 Gold-B measurements |
| Data pipeline | Bronze (immutable) → Silver (flagged) → Gold / Engineering Layer → Feature Store; everything point-in-time, versioned, auditable |
| Lifecycle segments | Physics-based turn detection (not the unreliable ~2% flag) + **20 mm confirmed dia-jump replacement rule**; single source of truth in `compute_boundaries()` |
| ML algorithm | **C1_xgb (XGBoost)** wins every dim×horizon over persistence (B0) and ridge (B2); fixed hyperparameters, **no tuning on holdout** |
| Regression target | **Δ-mode** (`predict = anchor + Δ`), never absolute level; horizons 30/90/180 d |
| Classification target | **P(turn)** 30/60/90 d, kept as a separate head from the level regression (action interrupts the process) |
| Evaluation | Temporal point-in-time splits only; benchmark + fleet backtest + serving gates; **80% split-conformal intervals**; release requires beating baselines, no metric-chasing |
| Honesty | Physics flags **reported, never clipped**; blocked features never silently imputed; feature coverage + model version on every forecast |
| Integration | Dashboard is a future **module inside SLAM** — **no auth/identity built here**; API-first typed contract of record |
| Refusals | Diameter-ΔX regression, diameter-1016 alert ML, survival/RSF, deep learning, RUL — all explicitly blocked or deferred |

---

## 2. Product framing decisions

These decisions shaped every later one, so they come first.

- **The product is not "predict RUL".** `ml/docs/plan.md` reframed the ask from a single
  RUL number into three connected models: *current health → root cause ("why") → future
  prediction*. The engineer-facing deliverable is the **trajectory** — expected wear over
  30/90/180 d with confidence, residual evidence, and time-to-action
  (`dashboard_roadmap.md:387-390`).
- **No causal claims.** Historical data gives correlations; output is phrased as **likely
  contributing factors**, never definitive causes (`ml/docs/plan.md:343-385`,
  `ml/README.md:79`).
- **Three signals, never collapsed.** P(turn), wear state, and limit proximity are kept
  separate; P(turn) is shed-maintenance *behaviour*, not an engineering failure threshold,
  so it is never the sole ranking signal (`dashboard_roadmap.md:41-44, :189`).
- **Physics-informed features preferred** over raw inputs: wear rate, acceleration, curve
  exposure, reprofiling depth, time-since-reprofiling (`ml/docs/plan.md:205-251`).
- **The trajectory (flange/root/tread) is the product target; diameter is diagnostic.** A
  wheel is turned/condemned on `max(flange, root, tread)` wear; diameter is a consequence
  (`ml/docs/contracts/wheel_profile_lifecycle_contract_v1.md:21-37`,
  `dashboard_roadmap.md:387-390`).

---

## 3. Cohort & scope decisions

- **WAP7 only.** Cohort resolved via `LocoTypes.LotTypeName = 'WAP7'` → `LomType = 9`
  = **2,317 locos** (2026-07-24 lookup). An earlier `LomNumber LIKE '30%'` denominator of
  829 was wrong and replaced; the cohort name must never be hard-coded as a type code
  (`ml/docs/entity_relationships.md:16-18`, `ml/validation/candidate_source_validation.md:8-13`).
- **Cohort-first extraction contract.** `experiment.cohort` in
  `configs/experiment.yaml` → `data/bronze/cohort_locomotives.parquet`; every domain query
  joins on the stable `LomId` (`ml/docs/entity_relationships.md:46-55`).
- **Identity key decisions** (`ml/validation/candidate_source_validation.md:276-316`):
  - `wsmEquipmentId` = `EmrId` is the stable per-wheelset key (100% maps to
    EquipmentMasterRegister).
  - `wsmWRId` is a per-measurement register reference re-issued each run (changes between
    adjacent measurements 99.8%) — using it for per-wheel counting produced a contamination
    artefact (99.4% of intervals = exactly 6). Correct join is `wsmWRId = LwrId` (99.98% of
    interval endpoints).
- **Wheelset universe.** 19,167 wheelsets across 2,180 Gold-B locos; WES v1.0 built from a
  1,165,641-measurement source universe (`ml/model_datasets/v3/wheel_engineering_state_card_v1.0.md:4`,
  `ml/docs/executive_summary_2026-08-07.md`).

---

## 4. Data segment decisions

### 4.1 Bronze → Silver → Gold pipeline

- **Bronze is immutable** raw source snapshots; no cleaning or business logic
  (`ml/silver_gold/README.md:17`).
- **Silver** cleans, deduplicates, quality-flags, and keeps lineage to Bronze; preserves raw
  values; quarantined vs accepted-with-flags split
  (`ml/configs/data_contracts.md:11-16`).
- **Gold is not a catch-all** — products are named by the engineering question they answer
  (Business Truth, Inspection Intervals, Operational Exposure, Feature Store)
  (`ml/README.md:30`).
- **Quality-flag taxonomy:** `valid`, `invalid_timestamp`, `sentinel_date`,
  `impossible_value`, `duplicate_record`, `missing_required_field`
  (`ml/docs/silver_gold_pipeline_technical_details.md:63-70`).
- **Point-in-time rule everywhere:** never use future measurements to compute past features;
  feature score boundary = `interval_end_timestamp` (`ml/docs/silver_gold_pipeline_technical_details.md:84-87`,
  `ml/feature_store/feature_store_contract.md:25-26`).
- **Versioning discipline:** Bronze never modified; Silver carries contract version + flags;
  feature/label/model datasets each version independently and released artifacts are
  immutable (`ml/docs/continuous_evolution_guide.md`).

### 4.2 Business Truth v1.0 (identity & assignment)

- **Timeline grain is equipment/wheelset-candidate**, keyed by `wheelset_equipment_id` —
  explicitly **not** individual physical wheel until `wsmEquipmentId` semantics are approved
  (`ml/releases/business_truth_v1.0.md:16-17`).
- **Tiering:** Gold A (single interval + validated measurements → ML),
  Gold B (single valid interval + accepted Silver → analytics),
  Gold C (no/multiple intervals → audit only) (`ml/configs/wheel_timeline_contract.md:7-11`).
- **Eligibility rule:** `start <= measurement_time <= end` (open-ended if null end);
  **no arbitrary choice between overlaps** — a measurement with multiple valid intervals goes
  to Gold C, never a picked winner (`ml/configs/wheel_timeline_contract.md:17-18`).
- **Coverage / exclusion policy:** **271,350 / 319,707 (84.87%)** measurements have exactly
  one valid assignment interval (Gold B). Exclusions retained for audit: 45,211 no-interval +
  3,146 ambiguous. The 821,575 full-fleet measurements outside the WAP7 universe are reported
  separately, not misclassified (`ml/validation/wheel_identity_validation.md:63-68`,
  `ml/validation/engineering_truth_validation.md:28-30`).
- **Evidence:** `LocoEquipments` is NOT a history table (static joins not historically
  correct); `LocoEquipmentsHistory` closes the gap — 97.44% of measurement equipment IDs have
  history, 77.95% match exactly one interval (`ml/validation/wheel_identity_validation.md:30-61`).
- **Verdict:** **PASS WITH KNOWN LIMITATIONS** — allowed to build intervals/coverage; wear,
  health, RUL and ML stayed blocked (`ml/validation/engineering_truth_validation.md:97-109`).

### 4.3 Inspection Intervals v1.0

- **Definition:** one consecutive inspection pair for the same wheelset candidate, same loco
  at both endpoints, strictly positive duration, Gold-B endpoints; failures retained with a
  reason (`ml/configs/inspection_interval_contract.md:3-8`).
- **Build result:** 252,183 consecutive pairs → **225,262 (89.33%)** Gold-B intervals;
  26,921 Gold-C exclusions (20,229 non-positive-duration + 6,692 loco changes)
  (`ml/docs/initial_plan.md:499-507`).
- RTIS/weather/track enrichment deferred to later contract versions — v1.0 establishes only
  trusted temporal boundaries (`ml/configs/inspection_interval_contract.md:14-15`).

### 4.4 Operational Exposure & the RTIS distance decision

- **Grain:** one released Gold-B interval; boundary `start < event <= end`. Emits RTIS
  emergency-source counts, job-card creation counts, RTIS reporting metadata.
- **Distance blocked by design:** `distance_km` must be null with status
  `BLOCKED_PENDING_SOURCE_CONFIRMATION` — no downstream feature may override
  (`ml/configs/operational_exposure_contract.md:3-12`).
- **Why RTIS was treated cautiously** (`ml/docs/rtis_semantics.md:36-98`): `RlkdTotalDistance`
  is **not** a lifetime cumulative counter (daily maxima increase 651,168 / decrease 659,464);
  duplicate business reports exist (121,283 repeated keys); gaps up to 546 days. Interim
  handling: never sum divisions, never difference across dates, never attach interval km.
- **Alternative distance sources rejected:** `MovementRegister` (billion-scale outliers,
  57,127 continuity breaks), FOIS GPS empty; rail km stays blocked until an authoritative
  station-to-track network is acquired (IR Geoportal candidate)
  (`ml/docs/initial_plan.md:547-574`, `ml/docs/distance_recovery_plan.md`).
- **Upgrade (2026-08-05):** senior domain review confirmed sensor-derived movement;
  RTIS owner approved the **deduped per-loco-per-day SUM rule** (sub-10 km = shed/stabling;
  15,540 of 29,229 low-km blocks matched FOIS shed evidence) → distance features became
  buildable in dataset v2 (`ml/docs/rtis_daily_distance_revalidation.md:28-45`,
  `ml/model_datasets/v2/dataset_card_v2.0.md:36`).

### 4.5 Lifecycle segmentation (the segment decision this project is most identified by)

**Governing contract:** `ml/docs/contracts/wheel_profile_lifecycle_contract_v1.md`.

- **Grain:** one wheelset lifecycle segment between turning/replacement boundaries.
- **Turning decision is wear-driven, NOT diameter-driven** — condemning on `max(flange, root,
  tread)` (flange 3.0 mm, root 6.0 mm, tread 6.5 mm); diameter floors 1020 mm safe-end /
  1016 mm dead-end / 1096 mm new-dia reference. **Wear values ratified from the Wrpld table
  2026-08-19** (`ml/configs/limit_register_v1.json`); earlier root 3 mm superseded
  (`wheel_profile_lifecycle_contract_v1.md:21-37, :78-80`).
- **Turn detection is physics-based, not flag-based** (`build_lifecycle_segments.py:6-13`):
  the turning flag appears on only ~2% of rows and = 0 across whole wheelsets; a flag gate
  discarded most real machining cuts. A reliable TURN EVENT = a flagged row with a dia cut in
  **[1, 25] mm** AND (flange or root) wear restored by **≥ 0.2 mm**. Unflagged rows need a
  stricter `TURN_CUT_UNFLAGGED_MIN = 2.0` to suppress sub-resolution noise;
  `MAX_INTER_EVENT_DAYS = 180` caps pre/post pairing.
- **Replacement detection (P0.2 fix):**
  - `REPLACEMENT_DIA_JUMP_MM = 20.0` — consecutive same-wheelset **mean**-dia up-jump ≥ 20 mm
    is a replacement candidate.
  - Confirmed when BOTH raw sides (`wsmDia1` AND `wsmDia2`) jump ≥ 20 mm **OR** the new level
    is **sustained** by the next measurement within `REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM = 10.0`
    (excludes one-off spikes).
  - Replacement = `wsmProvDate` change OR wheel-age reset OR confirmed dia-jump
    (`ml/models/phase5/build_lifecycle_segments.py:68-75, :117-169, :209-217`).
- **Single source of truth:** `compute_boundaries()` is shared by the segment builder,
  `build_degradation_substrate.py`, and serving `features.py` — duplicated thresholds were
  removed (`ml/docs/ml_correctness_analysis.md:92-97`, `dashboard_roadmap.md:79-85`).
- **Post-turn eligibility (k=3d):** rows where a turn/replacement occurs within 3 days after
  are dropped — the row is the wheel parked for machining (`wheel_profile_lifecycle_contract_v1.md:93-100`).

**Before → after the P0.2 fix** (`ml/docs/ml_correctness_analysis.md:76-115`):

| Measure | Before | After |
| --- | --- | --- |
| Replacement flags | 18,715 | 22,837 (+4,122) |
| Dia up-jumps ≥ 20 mm missed | 4,127 (52.1%) | **5 (0.06%)** |
| Segment count | 39,971 | **44,093** (+4,122) |
| Rising dia targets @180d | 5.04% (median +26 mm) | **1.81%** (median +3.3 mm) |
| Contaminated anchors @180d | 71% | 14.9% |

- The missed jumps were genuinely real replacements: median +48.5 mm, 99.3% both-sides,
  68% sustained, only **5 noise** (`ml/docs/ml_correctness_analysis.md:98-99`).
- **Version sensitivity:** the 44,093 figure is specifically the post-replacement-confirmation
  build. The earlier flag-gated run recorded 39,971 segments / 3,237 turns
  (`ml/models/experiments/v5/event_study_summary.json`). Always cite which boundary build a
  segment count belongs to.

### 4.6 Degradation substrate (segment-aware training targets)

- Anchors = frozen within-lifecycle rows (**239,684**); transient (k=3 d) exclusion removed
  30,855 rows (12.87%); horizon targets = last same-segment measurement strictly inside
  `(t, t+H]` (`build_degradation_substrate.py`). Turn-probability substrate: 220,000 anchors /
  15,576 wheelsets, train cutoff 2024-08-12 (`turn_probability_manifest.json`).

### 4.7 Dataset versioning (v1.0 → v3)

- **v1.0:** 202,237 rows, 58 X-features, grouped split by median interval-end per wheelset.
  Known limitation: raw sentinel outliers (|Δ| up to ~1090 mm / 2047 mm).
- **v1.1:** parent immutable; +38 features (geometry `geom_*`, physics `phys_*`, wear trends);
  physics join 99.50%; RMSE 22.88 → 15.69 (−31%). `geom_*` was the single largest contributor;
  `phys_*` largely overlapped (corr ≈ 1.0).
- **v1.2:** parent immutable; **label spec 1.0.1** quarantines endpoints with `wsmDia1` outside
  **[1000, 1100] mm** (65 rows). Reason: physically-impossible endpoints carried ~30% of total
  regression MSE; after quarantine max |Δ| = 80.30 mm.
- **v2:** parent immutable; +19 columns (approved RTIS safe-daily distance features + WS3
  experimental wear-per-km). `weather_exposure_index` NOT materialised (PENDING);
  missing rates up to 86.1% (RTIS window starts 2023-02-06).
- **v3 = Wheel Engineering State v1.0** (FROZEN 2026-08-06): **271,350 rows × 69 columns**,
  grain = one Gold-B attributable inspection measurement, **measured state only — no margins,
  no labels**; per-field quality codes; builder refuses to overwrite; manifest SHA256-pins
  sources (`ml/model_datasets/v3/wheel_engineering_state_card_v1.0.md`).

### 4.8 Feature Store decisions

- **Admission rule:** materialise only features with status `READY`,
  `READY_WITH_CAVEAT`, or `READY_FOR_MATERIALISATION`; `PENDING`/`BLOCKED`/`FUTURE` are
  recorded as excluded and **cannot appear as columns** — blocked features are never silently
  imputed (`ml/feature_store/feature_store_contract.md:7-14`).
- **Outputs:** `feature_store_v1.parquet` + `feature_registry.json` + `lineage.json`
  (SHA-256, grain, PIT rule) + coverage + quality + generated catalog.
- **Status inventory:** 2 READY, 11 READY_WITH_CAVEAT, 7 READY_FOR_MATERIALISATION;
  **BLOCKED** = `wear_rate_mm_per_day`, `wear_rate_mm_per_km`; **PENDING** =
  `weather_exposure_index`; **FUTURE** = `curve_severity_index`, `wheel_health_index`;
  `interval_distance_km` upgraded after the 2026-08-05 owner sign-off
  (`ml/configs/engineering_feature_specification_v1.json`).
- **Release count context:** initial release "7 admitted / 7 excluded" (2026-07-28); expanded
  build (2026-08-03) shows 18 approved / 6 excluded — both are documented; cite with date.

### 4.9 Data-quality decisions

- **Plausibility windows are quality filters, NOT condemning limits** (dia 1000–1100,
  flange thickness 10–50, root 0–30, tire thickness 5–100, gauge 1300–1700)
  (`ml/docs/wheel_engineering_state_specification_v1.0.md:59-69`).
- **Quality-code taxonomy:** `OBSERVED_VALID` / `MISSING` / `IMPLAUSIBLE` /
  `SEMANTICS_BLOCKED` / `NOT_APPLICABLE`. Blocked fields are preserved raw —
  "availability is not semantic validity" (`wheel_engineering_state_specification_v1.0.md:49-57`).
- **Zero-value handling:** exact 0.0 raw readings are placeholder/missing (~34% of
  `wsmThread` rows carry literal 0.0); excluded per-side before side-mean
  (`build_lifecycle_segments.py:108-112`).
- **Measurement noise / repeatability floor** (label audit): same-wheelset re-measured within
  1 d → median |dia delta| = **2.91 mm** (physical 1-day wear ≈ 0.1 mm) → the continuous
  diameter label is ~95% noise at single-interval level. Trajectory-product noise floor
  (σ_single = std/√2): flange **0.114**, root **0.105**, thread **0.066**, dia **0.052 mm**
  (`ml/docs/ml_correctness_analysis.md:224-226`).
- **Consequence:** `next_interval_large_loss_flag` excluded from primary outcomes;
  "No continuous-diameter-delta regression is a Phase 3 success target"; Phase 4 explicitly
  closes diameter-curve regression (`ml/docs/phase3_target_evaluation_contract_v2.0.md:77, :85`,
  `ml/docs/phase4_plan.md:19, :52`).
- **Validation evidence packs** are mandatory per product release: identity, temporal
  integrity, business rules, join coverage, event-ledger validation
  (`ml/validation/README.md:5-18`). Event-ledger DQ: trajectory is the classifier
  (`delta <= +3 mm` never emits an event; >+10 mm + persistence + corroborator →
  CONFIRMED); `flag2` is high-recall/low-precision (16.2%) and never auto-confirms
  (`ml/validation/event_ledger_validation.md:46-65, :82-90`).

---

## 5. Model training decisions

### 5.1 Algorithms

- **C1_xgb (XGBoost) is the production model** — chosen because it beats **B0 = persistence**
  and **B2 = ridge** on every dimension × horizon in the v5 benchmark (e.g. root@30d MAE 0.611
  vs persistence 0.715; the gap widens at 90/180 d) (`ml/models/experiments/v5/degradation_benchmark_report.md`).
- **B0 persistence** is the release gate baseline ("state stays"); production must beat it.
- **B2 ridge (`alpha=1.0`)** is the linearised "smart baseline"; C1 must also beat it
  (`ml/models/experiments/v3a/maintenance_risk_report.md`).
- Classifier comparison (logistic, RF, XGB, CatBoost) → **XGBoost won every horizon**
  (`ml/models/experiments/v3a/maintenance_risk_report.md`).
- **Turn-policy head does NOT use ML point predictions:** `B − A` (cut action) is not
  point-predictable; static `B1_shed` historical shed/reprofiling rates are used for policy
  simulation (`ml/models/experiments/v5/turn_policy_benchmark_report.md`).

### 5.2 Targets & horizons

- **Regression in Δ-mode:** the model regresses *change* over the horizon; the API serves
  `anchor + delta`. This removes level-dominance (absolute dia R² was level-driven, not trend)
  (`ml/docs/ml_correctness_analysis.md:276-279`, serving `manifest.json` target = "delta").
- **Dimensions:** flange / root / tread (limits 3 / 6 / 6.5 mm).
- **Degradation horizons: 30 / 90 / 180 d.**
- **P(turn) horizons: 30 / 60 / 90 d** (binary: will be re-turned within horizon; calibrated
  probability).
- Long-horizon (180/365 d) experiment targets exist but are **not served** — the contract
  pins the served horizons (`ml/docs/phase3_target_evaluation_contract_v2.0.md`).

### 5.3 Train/test splits (temporal only)

- **No random splits — temporal point-in-time splits only**, features/targets constructed
  using only information available at the forecast date
  (`ml/docs/phase3_target_evaluation_contract_v2.0.md` §6.1, §7).
- **Train cutoffs (everything after is held out):**
  - Degradation serving model: **2025-11-24**
  - Turn-probability serving model: **2024-08-11**
- **Frozen chronological 80/20 holdout** for the clean gate (persistence MAE reference
  **1.9992 mm**) (`ml/docs/phase3c_clean_benchmark_plan.md`).
- **Rolling cutoffs** re-fit on monthly/quarterly windows, evaluated out-of-sample each
  window (stability 90d PR-AUC 0.3577 ± 0.0914) (`ml/models/experiments/v3a/rolling_stability_90d.md`).
- **Point-in-time fleet backtest:** historical fleet states replayed as-of date through the
  full serving chain (`build_fleet_backtest.py`).
- **Wheelset adaptation:** per-wheelset refits validated out-of-sample on later events
  (`build_wheelset_adaptation.py`).

### 5.4 Validation / evaluation

- **Benchmark layer:** unit benchmarks per head (degradation, turn-probability, turn-policy)
  produce JSON/report artifacts.
- **Regression metrics:** MAE/RMSE per (dim × horizon); pass/fail is *beating baselines*, not
  an absolute number.
- **Classification metrics:** **ROC-AUC, PR-AUC** (extreme class imbalance), Recall@top-k%.
  P(turn) @30d ROC-AUC **0.885**, PR-AUC 0.114, turns captured top-5% **50.8%**
  (`ml/docs/ml_correctness_analysis.md:180-193`). Per-shed AUC spread 0.31–0.95 → shed context
  matters.
- **Degradation quality:** wear dims MAE ≈ monthly wear magnitude (flange 0.22–0.25 mm,
  root/thread 0.57–0.72 mm), R² 0.16–0.41, Spearman 0.43–0.66 → **useful for ranking and
  direction, NOT precise absolute-level claims**. Dia after fix: MAE 2.15–4.43 mm,
  R² 0.87–0.95, but ΔR² ≈ 0 (level-dominated by anchor) (`ml/docs/ml_correctness_analysis.md:134-175`).
- **80% split-conformal intervals** on the Δ-model, coverage verified 77–85% on test
  (flange/root slightly wide-conservative, thread on target)
  (`ml/docs/ml_correctness_analysis.md:234-246`).
- **Operational capture@k:** label = actually turned within H days; top-10% predicted
  flange/root/thread wear captures **58–93%** of turned wheelsets at 90d (thread 0.93,
  flange 0.84, root 0.58) (`ml/docs/ml_correctness_analysis.md:248-253`).
- **Calibration (ECE)** reported for probability heads.

### 5.5 Serving architecture

- **Artifact set per model:** `model.joblib` + `encoder.joblib` + `features.json` (ordered
  feature list) + `manifest.json` (target mode, train cutoff, horizon, dim, features).
- **Model version = content hash** of the artifact set; dashboard loads the exact hashed
  manifest → rollback-able (`dashboard_roadmap.md:160-172`).
- **Fail-fast schema validation:** `service.validate_serving()` runs at app import and raises
  on missing manifest/features/encoder/model or wrong dim×horizon grid; non-fatal warnings on
  `/health` and `/config` (`dashboard_roadmap.md:166-168`).
- **Rebuild is scripted, deterministic** (`build_serving_models.py`,
  `build_turn_probability_serving_models.py`, substrate builders separate) — no ad-hoc
  retraining in production.
- **Physics flags reported, never clipped:** `predict_degradation` attaches
  `implausibility_flag` per forecast (wear dims `< current − 0.05 → wear_better_than_current`;
  dia `> current + 0.001 → increasing_diameter`).

### 5.6 The two heads (hazard + level separation)

- **Degradation head (Layer 2, regression):** how fast wear proceeds — for condition-based
  scheduling.
- **P(turn) head (Layer 4, classification):** probability of re-turn within 30/60/90 d — a
  hazard/action head for resource/turn-policy planning.
- **Rationale for keeping them separate:** the turn action *interrupts* the wear process;
  the two heads have different targets, leakage risks, and calibration needs. A merged
  "hazard + level" model was rejected. Separate train cutoffs, separate validation.
- **Both suppress inference inside the k=3d post-turn window.**
- **Tail-probability head (v3f, experimental):** "root will exceed 3 mm within horizon"
  (AUC 0.862, ECE 0.012), kept as early-warning, validated separately. **SUPERSEDED on the
  limit (2026-08-19):** the Wrpld register sets root condemning = 6.0 mm; the Phase 4
  root-constraint target is `root > 6 mm` (`risk_event_contract_v1.md` v1.1). The 3 mm
  experiments remain as historical record only.

### 5.7 Hyperparameters & features

- **Fixed C1_xgb hyperparameters, identical everywhere** (no tuning loop):
  `n_estimators=400, learning_rate=0.08, max_depth=6, subsample=0.85, colsample_bytree=0.85,
  tree_method="hist", random_state=42`.
- **No hyperparameter search:** the clean-benchmark plan explicitly forbids tuning on the
  holdout ("no metric-chasing"); parameters frozen from v3a experiments + domain reasoning
  (`ml/docs/phase3c_clean_benchmark_plan.md`).
- **Feature set is contract + correctness controlled:** pins in `features.json`; include
  feature-store inputs, cumulative distance, life-cycle counters, prior profile dims,
  last-turn info, asset metadata.
- **Leakage fix during correctness review:** a **post-turn distance gate** feature was
  removed (informative only for turned wheelsets).
- **No silent imputation:** rows whose features cannot be fully reconstructed PIT are dropped
  at substrate build.

### 5.8 Explicit refusals / "no-ML" gates

- **Retired v3b benchmark:** the 17.95 mm "win" was an alignment bug (real result 4.52 mm);
  formally retired, replaced by clean v3c (persistence 1.9992 mm gate)
  (`ml/docs/phase3c_clean_benchmark_plan.md`).
- **Diameter-ΔX regression closed:** not enough signal; not served (`ml/docs/phase4_plan.md`).
- **Diameter-1016 alert ML refused:** positive rate ~0.04% → uncalibratable/deployable
  (`ml/models/experiments/v3f/crossing_tail_probability_report.md`).
- **Survival / Random-Survival-Forest blocked** and **deep learning blocked** in
  `ml/docs/phase4_plan.md` (complexity not justified by data/accuracy).
- **Release gates:** (1) beat persistence on every served (dim, horizon); (2) beat ridge on the
  clean chronological holdout; (3) no tuning on holdout; (4) correctness review (leakage,
  implausibility flags) passes before serving; (5) feature/manifest contract validated at
  request time (missing features → rejection, not imputation).
- **Platform-level gate:** ML/RUL was deliberately **blocked** until physical-distance (RTIS)
  semantics and wheel degradation/wear business rules pass their release gates
  (`ml/README.md:56-61`).

### 5.9 The P0.2 correctness fix (the biggest single ML decision)

Diagnosed "why does the model predict increasing diameter" → three root causes
(`ml/docs/ml_correctness_analysis.md:39-63`):

1. **Missed-replacement contamination of the target** (data problem) — fixed with the 20 mm
   confirmed-jump replacement rule (§4.5).
2. **Level-dominated regression** (model problem) — fixed by moving to **Δ-mode**.
3. **Signal below the repeatability floor** (measurement problem) — managed by treating dia as
   a derived diagnostic, not the product target.

Result: increasing-diameter flag rate went from +8.8 pp above actual (30d) to +3.9 pp, and
90d/180d to ≈ 0 / −1.7 pp; dia MAE −14…−20% (`ml/docs/ml_correctness_analysis.md:160-173`).

---

## 6. Product / UI / API decisions

### 6.1 Product framing for the dashboard

- **Dashboard becomes a module inside the SLAM application.** Consequences: no auth/identity
  built here; invest in correct ML outputs, clean typed FastAPI contract, fleet engineering
  UI, deployment reproducibility (`dashboard_roadmap.md:9-20`).
- **API-first, integration-ready:** FastAPI layer is the contract of record, consumed by both
  the React UI and future SLAM UI (`dashboard_roadmap.md:48-49`).
- **One chart-data contract:** a single versioned backend contract (`/lifecycle`, trajectory
  chart v1) feeds both interactive ECharts and Matplotlib SVG exports; **no lifecycle/forecast
  transformation logic in the frontend** (`dashboard_roadmap.md:46-47, :217-226`).

### 6.2 Fleet snapshot & API

- **Fleet snapshot parquet** (19,167 rows + manifest): one row per wheelset with latest state,
  forecasts, P(turn), limiting dimension, provenance/staleness; rebuild scripted
  (`dashboard_roadmap.md:180-196`).
- **Risk signals kept separate:** P(turn) AND wear state AND limit proximity, never collapsed
  into one number (`dashboard_roadmap.md:189`).
- **Versioned typed API** under `/api/v1/...`: fleet overview / risk / search / shed / loco /
  wheelset overview / lifecycle / backtest; 32 Pydantic models; env-based config;
  env-configurable CORS allow-list (never hardcoded `*`); legacy unversioned aliases kept for
  migration (`dashboard_roadmap.md:198-215`, `P4_AUDIT_REPORT.md`).
- **Honest forecast surface:** every forecast carries model version (content hash), train
  cutoff, feature coverage, physics flags, conformal bounds; UI renders forecasts only when
  the P0.2 dia fix is deployed (feature flag) (`dashboard_roadmap.md:158-172`).

### 6.3 UI decisions

- **Risk-ranked fleet table** is the main daily view: current state, limiting dimension,
  P(turn) 30/60/90, wear/limit proximity, staleness; filters + sortable
  (`dashboard_roadmap.md:240-251`).
- **Trajectory is the primary chart:** per-dim observed series, dashed forecast continuation,
  conformal band, realised residual strip, as-of re-anchor selector, turn markers with
  pre/post dims + `dia_cut`, physics flags, model meta (`dashboard_roadmap.md:260-267`).
- **Turning probability cards** retain uncertainty context (fleet-backtest ROC-AUC per
  horizon) (`dashboard_roadmap.md:263`).
- **Subgroup stability policy:** wheelsets in a collapsed subgroup (111 collapse rows, mostly
  shed × root/thread) get a "reduced confidence" amber badge — point forecast shown but not
  decision-grade there (`dashboard_roadmap.md:146-151`).
- **Design system:** Inter font (self-hosted, offline-safe), off-white background, hairline
  borders, one restrained indigo accent, small labels, no drop shadows — "old-age smooth and
  calm", not flashy (`dashboard_roadmap.md:277-287`).
- **ECharts** replaces hand-rolled SVG; components are data-agnostic (consume the contract
  objects only, swappable) (`dashboard_roadmap.md:289-295`).
- **UX states:** skeletons, empty states, error-with-retry, staleness banner
  (`dashboard_roadmap.md:269-273`).
- **Exports:** Matplotlib SVG/PNG report exports rendered server-side from the same contract;
  CSV export of the chart-data contract (`dashboard_roadmap.md:309-313`).

### 6.4 Deployment / integration decisions

- **Reproducible install:** `pyproject.toml` at root (pinned deps + editable `dashboard`
  package + `wheel-dashboard` launcher); `requirements-lock.txt` = exact `pip freeze`; both
  must not drift (`dashboard_roadmap.md:337-365`).
- **Env-driven config only:** `WHEEL_HOST` / `WHEEL_PORT` / `WHEEL_CORS_ORIGINS` /
  `WHEEL_SNAPSHOT_PARQUET`; safe defaults (CORS = local dev origins, never `*`)
  (`P4_AUDIT_REPORT.md:13-26`).
- **No auth anywhere:** zero auth code in the backend; auth/RBAC/SSO deferred to SLAM host;
  module boundary is unauthenticated (`P4_AUDIT_REPORT.md:33-42`).
- **Docker only as one simple optional Compose** for reproducibility — not a deployment
  architecture phase (no Kubernetes) (`dashboard_roadmap.md:332-333`).

---

## 7. Decisions to refrain from (deferred)

Enterprise hygiene deliberately deferred so they do not block ML/dashboard work
(`future_work.md`):

- CI/CD, model registry (MLflow), drift/monitoring, orchestration (Airflow/Dagster/Prefect).
- Moving binaries out of git (DVC/LFS), secrets infra.
- SSO, RBAC, user management → **owned by SLAM host**.
- Test fixtures replacing real parquet reads (tests currently need a fresh clone rebuild).
- Single living status index (README / `current_place.md` / `project_status_table.md` /
  `plan.md` have drifted).
- Path-traversal fix in `loco_plots` and CORS hardening — flagged in `future_work.md:49-58`.

---

## 8. Open questions / caveats (tracked, not resolved)

1. **Distance-gate ambiguity:** `interval_distance_km` is approved for dataset v2
   materialisation, but the serving-path release gate status should be reconfirmed before
   relying on distance-derived features (`ml/docs/ml_correctness_analysis.md:315-318`).
2. **Replacement truth is heuristic, not source-authorised:** a source-authoritative
   replacement/repair record (event ledger) is the correct long-term fix
   (`ml/docs/ml_correctness_analysis.md:319-321`).
3. **Flange/root/tread condemning limits — RESOLVED (2026-08-19).** The Wrpld table is the
   authoritative wear register (`ml/configs/limit_register_v1.json`): flange 3.0 / root 6.0 /
   tread 6.5 mm, all APPROVED. The remaining open item is the **three-step action ladder**
   (attention / plan turn / turn now) per dimension, still pending C&W/standards
   (`domain_ask_wear_limits.md`).
4. **Track geometry** (curve/gradient severity) — no authoritative source acquired yet
   (IR Geoportal candidate) (`ml/README.md:60`).
5. **Segment counts are version-sensitive** — cite the boundary build whenever quoting
   segment/turn counts (§4.5).

---

## 9. Source index

| Topic | Primary source |
| --- | --- |
| Product framing | `ml/docs/plan.md`, `ml/docs/contracts/wheel_profile_lifecycle_contract_v1.md` |
| Roadmap (P0–P4) | `dashboard_roadmap.md` |
| ML correctness & P0.2 fix | `ml/docs/ml_correctness_analysis.md` |
| Data segments / lifecycle | `ml/models/phase5/build_lifecycle_segments.py`, `ml/configs/wheel_timeline_contract.md`, `ml/validation/*` |
| Pipeline & contracts | `ml/docs/silver_gold_pipeline_technical_details.md`, `ml/configs/data_contracts.md` |
| RTIS distance | `ml/docs/rtis_semantics.md`, `ml/docs/rtis_daily_distance_revalidation.md`, `ml/docs/distance_recovery_plan.md` |
| Dataset versions | `ml/model_datasets/v1.0|v1.1|v1.2|v2|v3/*` |
| Feature store | `ml/feature_store/feature_store_contract.md`, `ml/configs/engineering_feature_specification_v1.json` |
| Model training | `ml/models/experiments/v5/degradation_benchmark_report.md`, `ml/docs/phase3c_clean_benchmark_plan.md`, `ml/docs/phase4_plan.md` |
| Evaluation | `ml/docs/phase3_target_evaluation_contract_v2.0.md`, `ml/docs/model_evaluation_report.md` |
| Serving | `ml/models/phase5/serving/{degradation,turn_probability}/*`, `ml/models/phase5/dashboard/backend/build_serving_models.py` |
| Data quality | `ml/model_datasets/v2/label_audit_report.md` (repeatability floor) |
| Wear limits ask | `domain_ask_wear_limits.md` |
| Limit register (Wrpld) | `ml/configs/limit_register_v1.json`, `ml/docs/contracts/risk_event_contract_v1.md` (v1.1) |
| Integration audit | `P4_AUDIT_REPORT.md` |
| Deferred work | `future_work.md` |
| Deployment | `development/readme.md`, `development/dashboard/DEPLOYMENT.md` |
