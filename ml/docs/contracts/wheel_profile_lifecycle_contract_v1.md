# Wheel Profile Lifecycle Contract v1.0

**Status:** DRAFT v1.3 — governing contract for Phase 5 (Wheel Profile Lifecycle System).
Supersedes the Phase 4 assumption that diameter independently drives turning.
**Grain:** one wheelset lifecycle segment (between turning/replacement boundaries).
**Consumes:** `wheel_engineering_state_v1.0` (immutable, v3) + FOIS shed attribution.
**Versioned release:** `model_datasets/v5/` (under build).

## 0. Versioning and immutability

- `wheel_engineering_state_v1.0` remains frozen and immutable. This contract **extends**
  it with a lifecycle-segment layer; it does not mutate v1.0.
- Margins computed here are Phase-5 lifecycle artifacts, governed by the limit
  register in §3. They do NOT back-port into the v1.0 engineering-state dataset
  (whose §5 margin layer stays pending under v1.0 rules).
- A change to a limit, direction, or boundary rule is a minor version bump of this
  contract; a change to the segment grain or identity is a major bump.

## 1. Domain model (owner-confirmed, 2026-08-11)

Turning/condemning is decided on **wear** of three dimensions — NOT on diameter alone:

| Dimension | Field(s) | Wear limit (max, condemning) | Direction |
| --- | --- | ---: | --- |
| Flange wear | `wsmFlange1`, `wsmFlange2` | **3.0 mm** | lower is better |
| Root wear | `wsmRoot1`, `wsmRoot2` | **6.0 mm** | lower is better |
| Tread wear | `wsmThread1`, `wsmThread2` | **6.5 mm** | lower is better |
| Diameter | `wsmDia1`, `wsmDia2` | **1016 mm dead-end / 1020 mm safe-end** | larger is better |

- **Turning decision:** a shed turns a wheel when `max(flange, root, tread)` wear
  approaches the shed's operating trigger, which must stay within the wear limits.
- **Cut = B − A:** `B` = current wear at turn, `A` = shed's post-turn residual target
  (shed-discretionary, e.g. flange 4→0 or 4→2), subject to the engineering limit.
  Material removed during machining reduces diameter accordingly.
- **Diameter is a consequence:** `dia_after = dia_before − cut`. Re-profiling the
  profile restores wear (flange/root/tread down, flange thickness up) and lowers dia.
- **Wheel life:** time from provisioning (or first post-turn state) until dia crosses
  the floor. Expected **3–4 yr** for wear-adopted wheels ("Make in India") vs **6–7 yr**
  historically for thick-flange wheels.
  **Layer 1 outcome (2026-08-12):** NOT validated by the provision-cohort split specified
  in the Phase 5 plan — the fleet is >90% right-censored above the floor and observed
  crossers are dominated by wheels provisioned near-floor (median age at 1020 crossing
  0.2–0.6 yr for 2023–24 provisions; 1016 crossings effectively absent, n=4). Wheel life
  must be modelled as a censored survival outcome (Kaplan-Meier / censored median to
  floor, first post-turn anchor) or remain an unvalidated hypothesis. See
  `models/experiments/v5/profile_event_study_report.md` §6.

## 2. Lifecycle segment definition

For each wheelset, the measurement stream is split into **lifecycle segments**
delimited by turning or replacement events:

```
POST-TURN → inspection → … → inspection → TURN → POST-TURN → …
```

Boundary rule (resolves measurement-pairing ambiguity):
- a row with `turning_record_at_measurement == 1` marks a **turn boundary**;
- a **provision-change** (wsmProvDate change / equipment replacement) marks a
  **replacement boundary** (new wheel identity);
- both split segments; a segment is only released when it has ≥ 2 measurements.

Per segment, emit:
- `wheelset_equipment_id`, `locomotive_id`, shed, wheel position, profile class;
- `segment_index`, `n_prior_turns`, `provision_change_flag`;
- `start/end timestamp`, `days`, `km` (where available), `turn_flag`;
- start/end `wsmDia`, `wsmFlange`, `wsmRoot`, `wsmThread`, `wsmFlangeThickness`,
  `wsmWheelGauge` (side-mean of quality-gated values);
- per-dimension wear deltas within segment (end − start).

## 3. Limit register (approved 2026-08-11; source ratified 2026-08-19)

| Quantity | Value | Source |
| --- | ---: | --- |
| Flange wear condemning | 3.0 mm | Owner-confirmed 2026-08-11; **Wrpld table** (ratified 2026-08-19) |
| Root wear condemning | 6.0 mm | Owner-confirmed 2026-08-11; **Wrpld table** (ratified 2026-08-19) — supersedes any earlier 3 mm root figure |
| Tread wear condemning | 6.5 mm | Owner-confirmed 2026-08-11; **Wrpld table** (ratified 2026-08-19) |
| Diameter safe floor | 1020 mm | Owner: "safe end" |
| Diameter dead floor | 1016 mm | Owner: "true dead end" (matches doc constant) |
| New diameter reference | 1096 mm | Existing doc constant |

> **Audit trail:** the authoritative wear register is `configs/limit_register_v1.json`,
> sourced from the **Wrpld table**. Per Wrpld: flange wear range 0-3 mm (condemning
> 3.0 mm), root wear range 0-6 mm (condemning 6.0 mm), tread wear range 0-6.5 mm
> (condemning 6.5 mm). The earlier 3 mm root value (degradation_semantics Q8) is
> superseded by the Wrpld value of 6.0 mm.

Margins (Phase-5 layer only): `flange_margin = 3.0 − flange`,
`root_margin = 6.0 − root`, `tread_margin = 6.5 − tread`,
`dia_margin = dia − 1016`. **Limiting dimension** = the dimension with the
smallest normalized margin.

## 4. Point-in-time and leakage rules

- All features at a segment's prediction time use only data knowable then.
- Turning labels count only events strictly inside `(t, t+H]` per the Phase 4
  risk-event contract; no future facts.
- Provision/replacement boundaries are respected: no wear delta spans a boundary.
- **Post-turn eligibility (owner/senior rule, 2026-08-12):** training/benchmark
  rows must use the **after-turning (fresh, post-turn) measurement** as the state.
  Rows that sit in the transient "at-shed" state (about to be machined — the worn
  pre-turn inspection) are **excluded from training features**. Concretely: drop a
  row when a turning/replacement event occurs within `k` days *after* it (default
  `k = 3d`, configurable), because that row is the wheel parked for machining, not
  a normal operating state. This is applied **going forward** (Layer 2+); v4
  benchmark (Phase 4) stays frozen as committed (`75f54eb`).
- **Layer 2 degradation target (v1.2):** target wear at horizon `H` =
  last same-lifecycle-segment measurement value of the dimension strictly inside
  `(t, t+H]` (within-segment trajectory, no turn/replacement cross). Excluded
  (`NaN`) when no such measurement exists. This measures "wear growth if no
  machining action is taken" and keeps the degradation and turn-risk problems
  separate (Layer 4 owns P(turn)).
- **Layer 2 exposure:** segments carry days only; km exposure and km-based wear
  slopes are joined from the safe RTIS daily ledger (`distance_recovery` safe
  chain), not re-derived inside the segment builder.

## 5. Data-quality gates (inherited from v1.0 spec §4)

Only `OBSERVED_VALID` quality values enter state calculations. Plausibility
windows are quality filters, not limits: dia 1000–1100, flangeThickness 10–50,
root 0–30, tread 0–30 (source artefact removal only).

## 6. Prohibited in v1.0, allowed in v5 lifecycle layer

- v1.0 §5 margin columns remain prohibited in the v3 dataset.
- The v5 lifecycle layer may compute margins, limiting dimension, and turning
  risk using §3 register — but only as **model attribution / recommendation**,
  never "cause" (per Phase 4 contract §8 semantics).

## 7. Deliverables

| Layer | Artifact |
| --- | --- |
| 0 | `model_datasets/v5/lifecycle_segments.parquet` + manifest |
| 1 | `models/experiments/v5/profile_event_study_report.md` + `event_study_summary.json`, `event_study_turnpolicy.json` (plots in `models/phase5/report/events_*.png`, `turnpolicy_p*.png`) |
| 2–4 | Predictive core (Layers 2–4 per Phase 5 plan) |
| 5 | FastAPI + React dashboard |
| 6 | Corrective-action map + feature additions |

## 8. Changelog

| Version | Date | Change |
| --- | --- | --- |
| v1.0 | 2026-08-12 | Initial Phase 5 lifecycle contract: wear-driven turning model, cut = B−A, limits (flange 3 / root 6 / tread 6.5), dia floors 1016/1020, segment definition, PIT rules. |
| v1.1 | 2026-08-12 | Post-turn eligibility rule (§4): training uses after-turning state; transient pre-turn at-shed rows excluded (default 3d look-ahead). Applies Layer 2+; v4 remains frozen. |
| v1.2 | 2026-08-12 | Layer 1 gate verdict recorded (§1 wheel-life outcome, §7 artifact path corrected); Layer 2 degradation target defined as within-segment horizon state (§4); km exposure sourced from safe RTIS ledger (§4). |
| v1.3 | 2026-08-19 | Limit register source ratified to the **Wrpld table** (`configs/limit_register_v1.json`). Values unchanged (flange 3.0 / root 6.0 / tread 6.5); Wrpld is now the authoritative, auditable source and any earlier 3 mm root figure is explicitly superseded. |
