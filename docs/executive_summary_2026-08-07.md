# Railway Wheel Engineering Intelligence — Executive Summary

**Goal:** Reconstruct wheel engineering state from railway inspection + operational data, rank maintenance risk, and recommend corrective actions.

## What we built this week
- **Frozen Wheel Engineering State v1.0** — 271,350 audited inspections, 19,167 wheels, quality-gated, immutable.
- **Maintenance-risk benchmark (Phase 3A)** — first publishable ML result.
- **Engineering intelligence (Phase 3B)** — health index, estimated RUL, corrective action, fleet/shed dashboards.

## Headline results
| Result | Value |
| --- | --- |
| Diameter-prediction error (v1.0 → v2.0) | **23 → 14 mm** (~37% better) |
| Inspect top-5% riskiest wheels → capture of near-term turnings | **~48%** (vs ~2–4% random) |
| ROC-AUC (30/90-day maintenance risk) | **0.87–0.88** |
| PR-AUC large-loss detection (v1.0 → v1.1) | **0.84 → 0.93** |
| Fleet health index (median) | **73 / 100** |
| Urgent-action wheels identified | **368** |

## Why this is trustworthy
- Improvements measured on **held-out + rolling (production-simulated)** splits — not train-set artefacts.
- Every prediction is **quality-gated**; unknowns are explicit, never imputed.
- We predict **degradation and risk ranking**, not the shed's turning decision.
- **RUL is labelled estimated/relative** — absolute condemning limits are not yet approved.

## Honest blockers (data semantics, not model capability)
1. **Km exposure blocked** → wear is time-based, not per-km.
2. **No approved limit register** → absolute RUL not yet claimable.
3. **Flange / tread / QR fields** semantics-blocked.
4. **Survival modelling parked** until censoring is validated.

## Next
Per-shed "top-N to inspect" dashboards · explainability · track geometry · learned health index · survival only after semantics approved.

**Bottom line:** The platform foundation is frozen and auditable. The first benchmark is already operationally interpretable — and the path to a top research paper and real deployment is well defined (see roadmap).
