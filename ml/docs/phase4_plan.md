# Phase 4 — Production Maintenance-Risk Benchmark

**Status:** Open for execution · governing plan for Stage 4
**Owner:** Wheel Engineering Intelligence Platform
**Date:** 2026-08-11 (v1.0); 2026-08-19 (v1.1)
**Prerequisite:** Phase 3F verdict (what is / is not forecastable), frozen v3f substrate,
Event & Censoring Audit v1, `maintenance_event_specification_v1.0` (turning target),
approved root limit (**6 mm — Wrpld table**, `configs/limit_register_v1.json`;
supersedes the earlier 3 mm Q8 figure), pinned environment (`ayush`).

---

## 1. Framing — from "build more intelligence" to "prove the decision system"

Phase 3F answered the scientific question it was chartered to answer:

- **Diameter ΔX is not open-loop forecastable** at the required granularity —
  the conditional mean of the residual is ~0, persistence beats every arm, and the
  latent/mixed-effects probe (`720aaaa`) was falsified. This is the honest result and
  it is now a closed finding. **We will not return to diameter-curve regression.**
- **The tail / ranking framing works.** Root-limit crossing (`root > 6 mm`, the Wrpld
  condemning value — see `risk_event_contract_v1.md` v1.1) is the Phase 4 target; the
  earlier 3 mm tail probe (AUC ≈ 0.86, ECE ≈ 0.012, capture@top-10% ≈ 52%) was superseded
  when the Wrpld register fixed root condemning at 6.0 mm, and the existing Track A
  maintenance-realization target already ranked usefully at 30–180d (Phase 3A: 90d XGB
  PR-AUC 0.364, R@5% 0.48).

Phase 4 therefore stops adding intelligence and **proves the production decision
system**: given a wheel inspection today, can we reliably produce the top-N list of
wheels that need inspection within the next 30/90/180 days — using only information
available at that inspection?

> **Central production question**
>
> *Given a wheel inspection today, can we reliably rank which wheels are most
> likely to encounter an engineering constraint or maintenance realization within
> the next 30/90/180 days, using only information available at that inspection?*

> **The milestone**
>
> *Can we produce a trustworthy top-N inspection list?*

## 2. Phase 4 targets (two, frozen)

| id | Target | Horizon(s) | Event definition | Limit status |
| --- | --- | --- | --- | --- |
| A | Engineering-risk: root constraint | 30 / 90 / 180 d | `root > 6 mm` strictly inside `(t, t+H]` | **APPROVED** — Wrpld table (`configs/limit_register_v1.json`): root wear 0-6 mm, condemning = 6.0 mm, lower is better. Supersedes the earlier 3 mm Q8 value (2026-08-08) |
| B | Maintenance-realization: turning | 30 / 90 / 180 d | recorded turning (`wsmturning1 == 1`) strictly inside `(t, t+H]` | Approved event (`maintenance_event_specification_v1.0`) |

**Explicitly excluded from Phase 4 primary outcomes:**

- Diameter 1016 mm crossing — near-zero event in this fleet (≈0.04%); kept as a
  semantic gate, not a benchmark target.
- Flange limit crossing — limit not owner-confirmed; diagnostic only.
- Continuous diameter-ΔX regression — falsified in Phase 3F.
- Survival / Cox / Random Survival Forest — **blocked**; censoring semantics are not
  approved (`maintenance_event_specification_v1.0` §8). We do not pretend the
  observation process is known.
- Deep learning — no evidence the bottleneck is model complexity.

**Semantic gates are not Phase 4 blockers.** Dia 1016 and flange limits remain
gated as before, but target A uses the already-approved root limit and target B uses
the approved turning event, so the benchmark can start now.

**Data-source note (verified 2026-08-11):** the v3f column
`turning_record_at_measurement` is **all-zero**; the turning signal lives in WES
(`wheel_engineering_state_v1.0.parquet`, 5,246 `turning_record_at_measurement==1`
rows of 271,350). Stage 4-A must join WES turning events onto v3f rows via
`measurement_record_id` (present and complete in v3f) to build target B.

## 3. Hypotheses (Phase 4 answers)

H1. **Ranking dominance:** the production candidate beats the prevalence baseline on
    PR-AUC and on capture@5%/capture@10% at all three horizons.

H2. **Calibration:** candidate probabilities are calibrated (ECE below threshold) on
    every horizon — the score is a probability, not a rank-only index.

H3. **Transferability:** ranking survives a never-seen-loco holdout (wheels of
    locomotives absent from training) — reported as a **stress**, not a promise.

H4. **Stability:** rolling point-in-time results are stable across cutoffs; the
    report presents every cutoff, never only the best.

H5. **Attribution discipline:** per-wheel attribution names "likely contributors"
    (root margin, recent root degradation, days since turning, wheel age, historical
    maintenance pattern), never "causes". Track A and Track B meet here.

If the candidate does **not** beat prevalence — or transfer fails — that is the honest
result and the report says so. No tuning is performed to force a win.

## 4. Scope

- Risk-ranking only (Track A decision intelligence) + per-wheel attribution (Track B
  engineering state meets Track A). No new ingestion; frozen v3f substrate + Event Ledger.
- One production candidate (XGBoost / LightGBM) compared against exactly three baselines
  (§6). No model zoo.
- Report at 30/90/180 d for both targets. No production horizon is selected by this phase.

## 5. Deliverables

```text
docs/phase4_plan.md                                      (this plan)
docs/contracts/risk_event_contract_v1.md                 (frozen label/eligibility contract)
models/phase4/build_risk_benchmark.py
  -> model_datasets/v4/risk_benchmark.parquet            (+ SHA256 manifest)
models/phase4/run_rolling_risk_benchmark.py
  -> models/experiments/v4/rolling_risk_benchmark.json   (PRIMARY)
models/phase4/run_loco_holdout.py
  -> models/experiments/v4/loco_holdout.json             (transferability stress)
models/phase4/run_attribution.py
  -> models/experiments/v4/attribution.json              (likely-contributor features)
models/phase4/render_risk_card.py
  -> models/experiments/v4/risk_cards/                  (Wheel Risk Card artifact)
models/experiments/v4/quality_gate_report.md
models/experiments/v4/final_benchmark_report.md
```

## 6. Stage 4-A — Event contract (freeze first)

The label contract is now more important than the model. `docs/contracts/risk_event_contract_v1.md`
freezes, for **each** of the six (target × horizon) outcomes:

- **Eligible observation:** an inspection row with attributable wheelset and usable
  timestamp; within-lifecycle state only (no replacement boundary rows).
- **Follow-up window:** `(t, t+H]` in calendar days; horizon label rule inherited from
  `maintenance_event_specification_v1.0` §6.
- **Exclusion rules:** Unknown follow-up (observation window shorter than H with no event)
  excluded from that horizon's cohort; replacement ends observation, never fabricates an event.
- **Maintenance/reset handling:** target A uses the point-in-time root measurement
  (`margin = 3 − root`, root grows toward 3). Target B uses `wsmturning1 == 1`,
  equipment-day deduplication, `wsmturning2` is quality-only.
- **Missing follow-up:** labelled, counted, never imputed.
- **Leakage rules:** no future facts; no post-`t` measurements, events, jobcards, or
  timestamps; point-in-time cutoff = `t`.
- **Per-target prevalence / eligibility counts** recorded per horizon.

**Gate 4-A:** contract frozen, SHA-pinned, eligibility counts recorded.

## 7. Stage 4-B — Rolling production benchmark (PRIMARY)

Monthly point-in-time refits. Every prediction simulates *"what would we have known
on that date?"* — train only on outcomes complete by cutoff `T`, score only states
known by `T`, evaluate their realized future without exposing the future.

Models — exactly:

| id | Model | Note |
| --- | --- | --- |
| B0 | Prevalence / random ranking | required baseline; also defines random capture@k |
| B1 | Regularized logistic (state/context set) | required baseline |
| B2 | Margin-only logistic (current root margin) | today's B1, re-validated under rolling protocol |
| C1 | XGBoost / LightGBM candidate | **comparator, not automatic champion** |

Metrics per (target, horizon, cutoff):

- **PR-AUC (primary)**, ROC-AUC, Brier, ECE (calibration).
- **Capture@5%, capture@10%** = fraction of realized events among the top-k ranked
  states (event capture = contract §7).
- **Lift@5%, lift@10%**, precision@5%/10%, prevalence, n.
- Rolling summary reports **every cutoff** and the distribution across cutoffs; no
  headline-best reporting.
- Stability strata: calendar period, shed, wheel/profile type, measurement
  quality/missingness (§8 of the target contract).

**Gate 4-B:** rolling JSON written; candidate-vs-three-baselines table; no tuning.

## 8. Stage 4-C — Never-seen-loco stress (secondary)

Grouped-by-loco holdout: ~20% of wheelsets withheld from training (a wheelset never
spans splits). Answers whether we learn *general wheel behaviour* rather than *this
loco's history*. Reported as a stress; failure to generalize is reported, not hidden.

## 9. Stage 4-D — Attribution and Wheel Risk Card

- **Attribution:** feature attribution (SHAP or equivalent) on the candidate per
  wheel. Outputs are **"likely contributors" / model attribution — never "cause"**.
- **Wheel Risk Card:** a renderable artifact per inspection:

```text
WHEEL ENGINEERING RISK CARD
Wheelset / Loco / Inspection date
90-DAY MAINTENANCE RISK          ████████████░░  HIGH
ROOT CONSTRAINT RISK             ██████████░░░░  HIGH
LIMITING DIMENSION               ROOT
CURRENT STATE                    Dia / Root / Flange / ... (mm)
LIKELY CONTRIBUTORS              1 Root margin  2 Recent degradation
                                 3 Maintenance history  4 Exposure/history
ACTION                           → PRIORITY INSPECTION
MODEL CONFIDENCE                 (calibration band)
```

This is the first genuine end-to-end product: score + explanation + action.

## 10. Evaluation hierarchy (inherits target contract §6)

1. **Rolling production simulation = primary deployment evidence.**
2. **Grouped-by-loco holdout = generalization stress** (reported as such).
3. Strict chronological split = secondary deterministic frame only.

## 11. Guardrails

- No future facts in any feature; point-in-time cutoff at `t`.
- Survival / Cox / RSF stay **blocked** — censoring semantics not approved.
- No diameter-curve regression; no deep learning; no tuning to force a win.
- Attribution is "likely contributors", never causal claims.
- Conformal/calibration coverage = empirical temporal coverage, not a guarantee.
- Every cutoff reported; stability strata reported; no headline-best.
- Honest reporting: if the candidate loses to prevalence or fails transfer, that is
  the finding.

## 12. Definition of done (Phase 4)

```text
[ ] Risk event contract frozen (docs/contracts/risk_event_contract_v1.md)
[ ] Eligibility / follow-up / exclusion logic frozen, counts recorded
[ ] Rolling monthly benchmark implemented (primary)
[ ] Never-seen-loco evaluation implemented (stress)
[ ] Prevalence baseline
[ ] Regularized logistic baseline
[ ] Margin-only logistic baseline
[ ] XGBoost / LightGBM candidate
[ ] PR-AUC primary
[ ] Capture@5% and capture@10%
[ ] Lift@5% / lift@10%
[ ] Calibration (ECE) per horizon
[ ] Feature attribution (likely contributors)
[ ] Wheel Risk Card artifact
[ ] Final benchmark report (all cutoffs, stability strata)
```

Only after Phase 4 is green do we move to Track Geometry / Dynamic Load / Route
Exposure feature integration (Phase 5).

## 13. Progression

| Phase | Question | Status |
| --- | --- | --- |
| 3F | What is actually forecastable? | **answered** (dia ΔX: no; root/turning ranking: yes) |
| 4 | Can we reliably rank the wheels that need attention? | **next** |
| 5 | Can we explain and improve the ranking with route/load/operational exposure? | later |
| 6 | True time/distance-to-constraint, once censoring and all limits are defensible | later |

## 14. Change log

| Date | Version | Change |
| --- | --- | --- |
| 2026-08-11 | 1.0 | Initial Phase 4 plan. Two frozen targets (root constraint, turning realization) at 30/90/180d; three required baselines + one candidate; rolling primary; loco stress; attribution + Wheel Risk Card; survival blocked; diameter regression closed. |
| 2026-08-19 | 1.1 | Target A retuned to the Wrpld register: root constraint = `root > 6 mm` (was 3 mm). `configs/limit_register_v1.json` is the auditable source. Phase 4 datasets/artifacts labelled with `limit_root_mm`; date-stamped runs distinguish 3 mm (pre-register) from 6 mm. |
