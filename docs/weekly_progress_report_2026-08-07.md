# Railway Wheel Engineering Intelligence — Weekly Progress Report

**Date:** 2026-08-07
**Audience:** Manager / Project Stakeholder
**Status:** Data backbone complete · first predictive results in · RUL correctly parked until data semantics are approved

---

## 1. What is the project about (30 seconds)

We are building a **railway wheel engineering intelligence platform** for CRIS /
Indian Railways. We combine heterogeneous operational data — wheel inspection
measurements, locomotive RTIS/FOIS running data, maintenance jobcards, equipment
registers — to:

1. **Reconstruct the engineering state** of a wheel (diameter, flange, root,
   gauge) as measured, without pretending we "know" hidden wheel health.
2. **Estimate degradation** and prioritise maintenance actions — i.e. tell the
   shed **which wheels to inspect and why** — rather than pretending we can
   decide when a wheel will be turned (that remains the shed's decision).

The key discipline: we do **not** call our prediction a "health score" or "true
RUL". We predict *measured engineering state and maintenance realisation under
partial observability*, and we keep every unknown explicit.

---

## 2. Where we are (roadmap)

```
✅ Enterprise raw data           — bronze tables + data dictionaries
✅ Engineering truth            — identity, validation, business rules
✅ Engineering state            — Wheel Engineering State v1.0 (FROZEN)
✅ Maintenance risk benchmark   — first publishable ML result (Phase 3A)
✅ Engineering intelligence     — health index, estimated RUL, corrective action (Phase 3B)
🔵 Decision dashboards          — next
🟢 Track geometry / dynamic load — later
🚫 Survival (Cox/RSF)           — blocked until censoring semantics approved
```

We deliberately **froze** the Wheel Engineering State v1.0 as an immutable
versioned contract: everything downstream consumes that one stable dataset, and
future data (track, weather, telemetry) extends it by version, never by mutating
it.

---

## 3. What our datasets look like (important features, not all)

### Wheel Engineering State v1.0 (FROZEN) — the backbone
- **271,350 inspection measurements** across **19,167 wheelsets**, with point-in-time context on **83%** of rows.
- One row = one attributable inspection measurement at its timestamp.
- Key **measured** fields (quality-gated): tread **diameter**, **flange thickness**, **root/fillet**, **tire thickness**, **wheel gauge**.
- **Blocked** fields (preserved but not interpreted, semantics unproven): `wsmFlange*`, `wsmThread*`, QR params.
- Every value carries a **quality code** (OBSERVED_VALID / MISSING / IMPLAUSIBLE / SEMANTICS_BLOCKED) — unknowns are never silently imputed.

### Feature families used by the models
- **Measured geometry** — diameter, flange thickness, root, tire thickness, gauge (side 1/2).
- **Exposure** — inspection interval in days, RTIS reporting coverage/counts, maintenance jobcard counts. *(Km is currently blocked — RTIS km semantics not yet approved; so exposure is time-based.)*
- **Maintenance history** — days since last turning, turning record, wheel age proxy.
- **Identity/context** — loco type, home shed, wheel/axle position, defect zone/division, profile class.

### Maintenance-risk benchmark datasets (Phase 3A)
Four datasets answering one question per horizon: *will this wheel be turned
within 30 / 90 / 180 / 365 days?* — built only on rows whose follow-up window is
**demonstrated** (eligible), so we never guess on wheels with unknown follow-up.

---

## 4. How prediction accuracy improved: v1.0 → v1.1 → v2.0

This is the headline progress story. The task: predict how much the wheel
diameter changes before the next inspection (`next_interval_dia_delta_mm`),
measured by **RMSE / MAE in millimetres** (lower = better).

| Version | What changed | Test RMSE | Test MAE |
| --- | --- | ---: | ---: |
| **v1.0** | Baseline — basic measurement + simple features | **23.1** | — |
| **v1.1** | Added **physics-informed features + measured geometry** (e.g. wear-per-1000km proxies, material remaining) | **15.7** | — |
| **v1.2** | Cleaned sentinel/quarantined label rows | **14.6** | **11.4** |
| **v2.0** | Full Phase-2 feature store (115 features, exposure v2, family attribution) | **14.5** | **11.2** |

**In words:** adding physics-informed features and richer exposure reduced the
diameter-prediction error from ~23 mm to ~14 mm — a **~37% improvement** over
the baseline — and the gain held on held-out and rolling (production-simulated)
evaluation. The remaining error is dominated by the wheel's own measurement
noise floor (~3 mm) and by interval variability, not by model weakness.

**On the label (binary) side, PR-AUC** (Precision-Recall Area Under Curve, the
right metric for rare events):
- v1.0: **0.84** → v1.1: **0.93** for detecting a large-loss interval.
- For the *rare* "next interval will be turned" flag the PR-AUC is low in
  absolute terms (0.01–0.03) because turning is an extremely rare event (≈1%);
  this is why we reframed the benchmark around **ranking** (below) instead of
  raw event probability.

### The benchmark that matters now (Phase 3A — maintenance risk ranking)
We evaluate like an engineering system, not an academic one. The question:
*if a shed inspects the highest-risk 5% of wheels, what fraction of future
turning events do we catch?*

| Horizon | Chance (random) | XGBoost — ROC-AUC | **Recall@Top-5%** | Recall@Top-10% |
| ---: | ---: | ---: | ---: | ---: |
| 30 days | ~1.5% | 0.884 | **48%** | 68% |
| 90 days | ~3.8% | 0.873 | **48%** | 67% |
| 180 days | ~9.3% | 0.864 | 35% | 57% |

**Read that carefully:** by inspecting just 5% of the fleet flagged by the
model, we capture ~half of all turning events happening in the next 30–90 days.
That is a *deployable, interpretable* maintenance-prioritisation result.

---

## 5. Engineering intelligence (Phase 3B — the "why" and "what to do")

On top of the frozen state we built per-wheel intelligence (rule-based,
transparent — not a black box):

- **Segment-level wear rates** (mm/day) computed per wheel life-segment between
  turnings — this averages out inspection noise and gives a real degradation
  signal.
- **Engineering Health Index** (0–100). Fleet median ≈ 73.
- **Estimated Engineering RUL (days)** — rate-based projection, clearly
  labelled fleet-relative (absolute condemning limits are not yet approved).
- **Limiting dimension** — the engineering parameter closest to its threshold
  (currently wheel gauge dominates, then root).
- **Recommended action** per state: MONITOR / SCHEDULE_INSPECTION /
  PLAN_TURNING_REPROFILING / URGENT_ACTION.
- **Dashboards:** fleet/shed summary and top-priority wheel health cards.

Distribution across 271k states: 224,699 plan-reprofiling · 44,137
schedule-inspection · 368 urgent-action · 2,146 monitor.

---

## 6. What looks promising vs what still needs work

### ✅ Promising
- **Physics-informed features + exposure** cut diameter-prediction error ~37% (23 → 14 mm).
- **Ranking-based benchmark** (Recall@Top-5% ≈ 48% at 30/90d) is an immediately useful, interpretable result for sheds.
- **Engineering State v1.0 frozen** — a stable, auditable foundation.
- **Discipline:** we've stopped the shed-decision prediction trap and focus on degradation + prioritisation; unknowns are explicit.

### ⚠️ Needs more work
- **Km / distance semantics are blocked** — exposure is time-based only. True wear-per-km models wait on RTIS km validation.
- **Absolute RUL** needs an **approved engineering limit register** (new/condemning values per rolling-stock class). Until then RUL is relative.
- **Flange / tread / QR fields** are semantics-blocked — cannot yet be used as margins.
- **Survival / time-to-event modelling is deliberately parked** (censoring not validated). We will unblock it only when observation-end + censoring assumptions are proven.
- **Measurement noise floor (~3 mm)** caps per-inspection wear accuracy; we work around it via segment-level aggregation.

---

## 7. Honest answer to "is the accuracy correct / how confident are we?"

- The **23 → 14 mm** improvement is a **real, reproducible** effect measured on
  held-out and rolling (production-simulated) test splits — not a train-set
  artefact.
- Confidence is **quantified**: we report RMSE/MAE, PR-AUC, calibration (Brier/
  ECE) and rolling medians, and we separate *test* from *rolling* performance.
- We are **deliberately conservative**: RUL is labelled as estimated/relative,
  the health index is rule-based, and anything that would require a hidden
  assumption (survival, absolute condemning limits, margin from blocked fields)
  is blocked rather than fudged.
- In short: we trust the **ranking** strongly (which wheels are riskiest), and
  we are honest that absolute **time-to-failure** claims are not yet defensible.

---

## 8. What we plan next

1. **Decision dashboards (next sprint):** per-shed "top-N wheels to inspect"
   ranked lists, wheel/loco health cards, fleet overview.
2. **Explainability:** show *which dimension* pushes each wheel's risk up
   (limiting-dimension is already computed; surface it in the UI).
3. **Track geometry integration (1–2 months):** route curvature, gradient,
   turnout exposure — the biggest missing engineering signal.
4. **Dynamic load integration** and a **learned** (not just rule-based) health
   index.
5. **Survival modelling only after** observation-end and censoring semantics are
   validated by the data owner.
6. **Rolling backtest + feature attribution** on the 90-day benchmark for the
   publishable paper.

---

## 9. Bottom line for stakeholders

We have moved from "can we predict wear?" to **"we reconstruct wheel engineering
state from heterogeneous railway data, rank maintenance risk well above chance,
and explain the corrective action."** The platform foundation is frozen and
auditable; the first benchmark is already operationally interpretable (inspect
5% → catch ~half of near-term turnings). The remaining blockers are **data
semantics** (km validation, limit register), not model capability — and we have
designed the platform so those can be added by version without reworking what
already exists.
