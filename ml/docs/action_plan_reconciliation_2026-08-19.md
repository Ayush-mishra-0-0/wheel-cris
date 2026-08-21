# Action Plan Reconciliation — 2026-08-19

Source: senior assessment response (`SENIOR_ASSESSMENT_2026-08-19.md`) reconciled against actual
experiment artifacts (`ml/models/experiments/v1.2`, `v3`, `v1.2_survival`). This document is the
authoritative next-steps plan and supersedes open items from the review where noted.

## Closed findings (do not re-open)

1. **Label quarantine (v1.2)** — Done. Sentinel audit (Rule B: endpoint `wsmDia1` in [1000, 1100])
   subsumed Rule A; only 65 rows quarantined (55 train / 9 val / 1 test). Regression RMSE dropped
   from the v1.0 23.1 to ~14.6 on test (`v1.2/comparison.csv`: linear 15.09, elastic_net 14.96,
   HGB 15.20). Review's v1.0 numbers (23.1 / PR-AUC 0.0127 / C-index 0.539) are historical.
2. **Two-stage regression (v3 label decomposition)** — Done, null result. Single-stage
   MAE 11.397 / RMSE 14.566 / R² 0.530 vs combined 11.451 / 14.665; stage-2a clean-only
   5.782 / 7.873; stage-1 detection PR-AUC 0.9274. Two-stage gives no net gain (`v3/label_decomposition_summary.md`).
3. **Proper survival (CoxPH, full right-censored, v1.2_survival)** — Done. C-index
   val 0.5443 / test 0.4896 ≈ chance on the full censored train (test censor 91.8%), with
   per-wheelset observation-end censoring (time = last measurement − interval_end). The old 0.539
   was survivorship bias (HGB trained on uncensored rows only). **RSF/GBSA deferred** until
   censoring semantics are approved — CoxPH at chance already answers the question.
4. **Early turning-flag classification (PR-AUC ≈ prevalence)** — Failure correctly abandoned as a
   primary target; live framing is ranking/prioritisation, not categorical prediction.

## Live priorities (ordered)

1. **Official Wrpld limits locked into all contracts & dashboard**
   - Flange 0–3 mm, Root 0–6 mm, Tread 0–6.5 mm, Dia 1016 mm
   - Reconcile residual hard-coding (no phantom "3 mm root").
   - Document source in the data contracts.
2. **Phase 4 ranking protocol (highest ROI)**
   - Freeze `risk_event_contract_v1` against the official limits
   - Rolling monthly benchmark (Capture@5 %/@10 %, ECE, every cutoff)
   - Never-seen-loco stress test
   - Wheel Risk Card + "likely contributors" attribution
3. **Materialise already-validated free deltas** (feature store v1.1+)
   - flange/root/gauge/tire thickness deltas, skid flags, abnormal-event counts — free signal,
     no new data ownership required.
4. **Distance blocker (highest-leverage non-ML task)**
   - RTIS owner sign-off on safe aggregation, or fallback chainage path.
   - `interval_distance_km` remains the ceiling; wear-per-day is only a proxy.
5. **UI: 6-wheel overlay + checkbox select/deselect (senior request)** — Implemented in
   `development/dashboard/frontend/src/OverlayPanel.tsx` (checkbox chips, primary/+dia toggle,
   CSV/PNG/SVG export). Remaining: fleet-snapshot rebuild to materialise calibrated columns.

## Explicitly deferred

- Native LGBM/CatBoost + grouped-temporal HPO (review item 7) — until ranking protocol is green.
- Further survival trees / complex survival architectures — until censoring semantics approved.
- Model registry / drift monitoring / full CI — until the decision product is stable.
- Multibody track-flexibility simulation — wrong time horizon.
- Do not force blocked features (distance, route/geometry) into models to inflate metrics —
  governance discipline preserved.

## Open action threads (tracked, not blocked)

- **Distance semantics**: RESOLVED for the serving path — the RTIS-safe
  `interval_distance_km` rule was owner-approved (2026-08-05) and is released
  to serving; see `docs/distance_serving_gate.md` (authoritative). Remaining
  open item is coverage improvement only.
- **PADX shed error enrichment**: ~11× error enrichment observed; documentation/reproduction memo
  pending (ties into live priority 3 deltas and 4 distance).
- **Survival numerator**: time to turning is a discretionary shed decision; survival re-opens only
  if a censoring-time basis is approved by the business.