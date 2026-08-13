# Phase 5 — Layer 1 Event Study: Gate Verdict

**Date:** 2026-08-12 · **Governing contract:** `docs/contracts/wheel_profile_lifecycle_contract_v1.md`
**Scope:** Layer 1 validation gate per Phase 5 plan ("mechanism visible → proceed; else report honestly").

## Verdict

**PASS WITH KNOWN LIMITATIONS → proceed to Layers 2–4.**

The wear-driven turning mechanism is visible in the data and the shed behaviour is
consistent with the contract's cut = B − A model. One contract claim — the 3–4 yr
vs 6–7 yr wheel-life split — is **NOT validated** as specified (censoring); see §6.

## Evidence

Source artifacts (plots in `models/phase5/report/`, JSON in this directory):

| Plot | Question | Result |
| --- | --- | --- |
| `events_trajectories.png` | wear grows within a segment? | Yes: flange/root/tread increase from segment start → end, bounded below limits |
| `turnpolicy_p4_sawtooth.png` | wear resets at turn, dia is the cost? | Yes: wear drops at turn, diameter falls by the cut |
| `events_cut_by_shed.png`, `turnpolicy_p3_shed_policy.png` | cut is shed-discretionary? | Yes: median cut varies by shed (≥20-event sheds show distinct policies) |
| `turnpolicy_p1_prestate_vs_cut.png` | cut ∝ pre-turn wear (B−A)? | Yes: positive relationship, cut clusters with pre-state |
| `turnpolicy_p2_rdso.png` | cut ≈ RDSO formula? | Partial: median residual −0.55 mm, in-tolerance 26.6% → formula undercuts; shed policy is dominant |
| `events_wheel_life.png`, `turnpolicy_p5_wheel_life.png` | turning = end of life? | No: turning is frequent (median 0.39 yr between turns); life is driven by cumulative dia cut |

## Key numbers

- 39,971 segments · 3,237 turning events · 1,649 wheelsets · 300 locos · median cut **7.0 mm**.
- **Limits held in the live fleet:** pre-turn flange p95 2.13 mm (>3: 0.15%), root p95 4.2 mm
  (>6: 0.03%), tread p95 3.25 mm (>6.5: 0.0%). No turn below dia floor 1016 / safe 1020.
  Sheds act on a trigger **well inside** the register limits (root median 2.88), i.e. the
  "approaching shed-specific threshold" behaviour the contract asserts.
- **Limiting dimension at turn:** root 2,039 · flange 990 · tread 208 → root/fillet is the
  primary constraint in production, consistent with root-dominant degradation.
- **Last-2y cohort (primary, ≥ 2024-08-12):** median pre-turn flange 0.8, root 2.6, tread 2.0;
  RDSO residual −0.29 (in-tol 30.9%); limiting dim root 770 / tread 204 / flange 146.
- **Shed attribution:** 80.6% of turns attributed (SLAM stay → FOIS station → home_shed
  fallback); coverage gap accepted per plan.

## What this means

- The Phase 4 assumption (diameter independently drives turning) is superseded: sheds turn
  on wear state, root first; diameter is the machining consequence.
- `post_turn_wear ≈ A + ε` per shed is a defensible Layer 3 target — shed policy is
  recoverable from pre-state + shed (Layer 1 evidence supports the B − A decomposition).
- Layers 2–4 (degradation, B−A, turn-risk) may proceed. The dashboard remains **not**
  labelled "predictive" until Layers 2–4 benchmarks land.

## Honest failures (report as asked)

1. **Wheel life (contract §1, "3–4 yr vs 6–7 yr") is NOT reproduced by the specified
   provision-cohort split.** Computing `wsmProvDate → dia ≤ 1020/1016`, split by provision
   year × profile class:
   - Floor 1020 crossers: median age at crossing 0.2–0.6 yr (2023–24 provisions), 1.6–3.2 yr
     (2020–22); tiny n at every cohort.
   - Floor 1016: effectively no crossings (n = 4 events total).
   - Only 5.4% of wheels are below 1020 today; the rest are right-censored, and the
     observed crossers are dominated by wheels provisioned already-near-floor. Linear
     extrapolation (P5c) is inflated by the first-turn cut.
   - **Action:** wheel life must be modelled as a censored survival outcome
     (Kaplan-Meier / censored median to floor, anchored at first post-turn state per
     contract §1), or the claim is formally unvalidated. Not a Layer 1 blocker for the
     predictive core.
2. **RDSO cut formula is a poor global fit** (26.6% in tolerance, median −0.55). Layer 3
   must therefore model cut with shed as a conditional factor, not rely on the closed-form
   formula.

## Reuse caveats for Layer 2

- Segments carry days but **no distance**; km exposure must be joined from the safe RTIS
  daily ledger for km-based wear slopes.
- `wheel_profile_2class` 57% null, `wheel_position_1_12` 57% null, `shed_any` 15% null on
  segments → categorical features will be sparse; keep native NaN semantics.
- Only 1,649 / 19,167 wheelsets ever turn → Layer 4 P(turn) will be heavily imbalanced.
