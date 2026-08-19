# Senior Assessment — 2026-08-19 (Filed)

> Filed alongside `SENIOR_REVIEW.md` (one-page product review) and `future_work.md`
> (deferred enterprise hygiene). This file preserves the external senior review of the
> Wheel Lifecycle Analytics Platform, followed by the **reconciled roadmap** reflecting
> everything changed on 2026-08-19 (Wrpld limit ratification).
>
> Status of the review itself: **addressed / partially addressed** — see the reconciliation below.

---

## Part 1 — The assessment (cleaned)

### 1.1 Data scale
- **WAP7 cohort: 2,317 locomotives, 19,167 wheelsets, 271,350 Gold-B measurements** (2014 → Jul 2026).
- **225,262 valid inspection intervals** after applying the inspection-interval contract.

### 1.2 What works
- **Diameter regression (Phase 3F, closed):** RMSE ≈ **14.5–15.7 mm** on the diameter ΔX task. Accurate in absolute terms but **unexciting** — most of the error mass sits far from the 1016 mm condemning limit, so it drives little maintenance value.
- **Large-loss PR-AUC 0.927** — the large-loss classification head is very strong; flags the truly condemned wheels with high precision/recall.
- **Maintenance ranking, Recall@Top-5% ≈ 48% (30/90 d)** — ranking near-term maintenance targets in the top-5% of the fleet is effective and is the operationally valuable result.

### 1.3 Protocol discipline
- **Protocol A vs B dual evaluation** — deterministic (A) and noisy (B) evals kept separate; a disciplined choice.
- **Feature Store: 7 features admitted / 7 excluded** — documented, auditable admission decisions.

### 1.4 Gaps / blocked items
- **Survival modelling blocked** pending unambiguous **censoring semantics** in the maintenance data.
- **RTIS km blocked** (distance recovery) — usable distance signal still unresolved.
- **Track geometry = the largest missing external dataset** — no curvature/gradient input; would materially improve wear-rate realism.

---

## Part 2 — Reconciled roadmap (as of 2026-08-19)

### 2.1 Limit authority — Wrpld table ratified (DONE)
- `ml/configs/limit_register_v1.json` is now the single **APPROVED** wear register, sourced from the **Wrpld table**:
  - **flange 0–3 mm** (3.0 condemning) · **root 0–6 mm** (6.0 condemning) · **tread 0–6.5 mm** (6.5 condemning) · diameter 1016 mm (unchanged).
- Earlier "root = 3 mm" figure (Q8, `degradation_semantics.md` §3.3) **superseded**; all Phase 4 code, the risk-event contract (v1.1), the lifecycle contract (v1.3), the dashboard `LIMIT_REGISTER`, the fleet-snapshot limiting-dimension logic, and the Engineering Health Index reference were updated to the ratified values and documented.

### 2.2 Phase 4 benchmark — re-run at the correct limit (DONE, with an honest caveat)
- Full pipeline rebuilt and re-executed with `limit_root_mm: 6.0` (dataset sha256 `8b0595…`):
  - **Turning (target B): PRODUCTION-READY.** 90 d C1 capture@10% **0.78**, ROC **0.925**; transfers to never-seen locomotives (hold-out ROC 0.950). This is the shipping use-case and **reproduces/improves the assessment's Recall@Top-5% ≈ 48 %** (C1 90 d capture@5% = 0.58).
  - **Root>6 mm (target A): NOT statistically operable.** At the true Wrpld limit the event is ~0.03–0.2 % of eligible rows; 30 d has **zero** evaluable cutoffs, 90/180 d show ROC ≈ 0.57–0.59 driven by a handful of events. **This is a prevalence limitation, not a modelling failure** — the earlier "learnable root" claim was an artifact of the superseded 3 mm threshold.
  - **Roadmap decision:** root stays **out of the production ranking**; turning + diameter margin carry the list. Revisit only if (a) a pre-condemning soft watch-band threshold is defined, or (b) prevalence data grows.
- **Still open from `domain_ask_wear_limits.md`:** the 3-step **action ladder** (attention / plan turn / turn now) per dimension — condemning hard stops are approved; the escalation ladder is not.

### 2.3 Deferred (carried from the assessment, unchanged)
- Survival modelling — wait for censoring semantics.
- RTIS km distance recovery — in progress (`ml/distance_recovery/`), not yet accepted.
- Track-geometry acquisition — continue pursuing (`ml/docs/ir_geoportal_acquisition_plan.md`); largest external-data gap.
- Model registry / drift monitoring / CI — remain on `future_work.md`.

### 2.4 Numbers this assessment should be read alongside
- Degradation C1 MAE (frozen test): root 0.43/0.48/0.54, flange 0.19/0.21/0.24, thread 0.38/0.47/0.57, dia 1.15/1.60/2.10 (30/90/180 d) — `SENIOR_REVIEW.md`.
- Wear-rate champion: −16 % aggregate no-turn error on flange/diameter, 0 % physically impossible forecasts.
- Diameter regression RMSE 14.5–15.7 mm (Phase 3F closed); large-loss PR-AUC 0.927.

---

*Last updated: 2026-08-19. Reconciliation of the review is tracked in `DECISIONS_REPORT.md` (question #3 resolved: flange/root/tread action limits ratified from Wrpld).*
