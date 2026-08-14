# One-page ask: numeric wear action thresholds (C&W / standards)

**From:** wheel-forecast project (engineering)
**To:** C&W / standards owners (IR/RDSO, shed inspection)
**Date:** 2026-08-14
**Status:** DRAFT — blocking "time to wear action" reporting

## The ask

Sign off **numeric action thresholds** for the three wear dimensions below,
each with a three-step action ladder. Without a signed number, the platform
can report a wear forecast but cannot state *"this wheelset needs attention /
turning in N days"* honestly.

## What is already approved

| Dimension | Hard stop | Direction | Status |
|---|---|---|---|
| Wheel diameter (dia) | **1016 mm** (condemning) | falls toward | **approved** |

## What we need (3 columns of numbers, ideally per profile class / loco type)

| Dimension | Unit | Attention (inspect) | Plan turn (scheduled) | Turn now (urgent) | Comments |
|---|---|---|---|---|---|
| Flange height | mm | ? | ? | ? | profile-class dependent |
| Flange thickness | mm | ? | ? | ? | usually the binding one for Co-Co |
| Tread / root | mm | ? | ? | ? | root measured together with flange |

Any of the following is a good start:

1. **Three numbers per dimension** (attention / plan turn / turn now) —
   preferred; unlocks the full action ladder.
2. **A single "plan turn" threshold** per dimension — minimum viable; we can
   show a two-state flag (OK / approaching).
3. **An existing standard/instruction reference** (e.g., IR wheel profile
   schedule, RDSO drawing or workshop manual) — we read the thresholds off it
   and come back to you with a proposed table for confirmation.

## Optional but useful

- **Horizon of interest**: are 30/90/180-day look-aheads the right
  granularity, or do you think in depot visit intervals instead?
- **Loco-type / profile-class specificity**: is one fleet-wide number fine, or
  should thresholds differ by profile class (e.g., 2-class vs 3-class) and
  loco type?
- **Tread hollowing vs flange**: do you also want a hollowing-depth action
  value, or is flange thickness the primary turn trigger?

## What we do with it (once provided)

1. Register each number in the **versioned LIMIT_REGISTER** (status:
   `approved`, owner, units) — surfaced in `/api/v1/config`.
2. Report **days-to-*action*** for flange/root/tread from the serving delta
   forecasts (30/90/180-day conformal bands), with the action ladder label.
3. Flag **fleet risk** counts per action tier in the fleet view.
4. Calibrate the dia condemning band (already live: 80% coverage at 30/90d).

## What stays blocked without it

- Per-wheelset "days to wear action" for flange/root/tread (today only dia
  has an approved limit).
- Fleet-level action-tier counts and prioritisation by urgency.
