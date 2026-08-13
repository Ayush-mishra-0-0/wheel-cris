# Phase 3 Step 0 — Maintenance Process Audit

## Decision

**Treat `wsmturning1` as an observed maintenance-realization target, not as directly observed engineering need.** It may reflect engineering condition, scheduled work, fleet-level action, and data-entry process.

## What the data can establish

- `42,492` turn-flagged measurement rows across `37,739` distinct wheelset-days; `4,753` rows are same-day duplicates.
- At a new turn flag, valid prior-measurement pairs have median diameter change -4.00 mm; 57.0% drop by more than 3 mm and 2.4% gain by more than 3 mm. The 40.5% at <=3 mm are compatible with minimum-cut reprofiling and must not be used to invalidate the event flag.
- 97.8% of linked turning wheelset-days co-occur with another turned wheelset on the same locomotive-day. This is evidence of possible fleet-level batching, not proof of its cause.
- A jobcard exists on the same locomotive-day for 36.3% of linked events and within ±1 day for 59.7%. This is temporal context only.

## What the data cannot establish

- The engineering criterion that triggered a turn: no wheelset-level reason code or first-limit-hit field is available.
- Whether turning was scheduled, preventive, emergency, capacity-constrained, or discretionary.
- A reliable completion time or a causal jobcard linkage: jobcards are locomotive-level and `SejCreatedOn` is creation time, not confirmed work completion.
- Whether a non-turning record represents a healthy wheel versus an unserved wheel waiting for workshop capacity.

## Engineering interpretation

Wheel reprofiling is a multi-constraint action: the material removed can be set by the limiting flange/profile/defect condition, not by a fixed diameter reduction. Indian Railways training material describes intermediate worn-wheel profiles specifically to reduce metal removal. Therefore, diameter delta is unsuitable as a turning-signature test or as a sole health target. The later Wheel Health State must be a vector of measured margins, not a single diameter score.

## Required domain-owner decisions before Target Specification v2

1. Provide the authoritative turning/reprofiling decision rule and limits by wheel profile/type.
2. Identify a wheelset-level maintenance action/reason/completion source, or formally state that none exists.
3. Define whether `wsmturning1` is recorded before, during, or after the physical turning operation.
4. Define replacement versus reprofiling and planned versus unscheduled maintenance semantics.
5. Confirm whether multi-wheel same-locomotive actions are policy batching and how they should be represented.

## Gate

Proceed with two explicitly separate constructs: (1) `wsmturning1` as an **operational maintenance-realization** target, and (2) a rule-based, uncertainty-labelled Wheel Health State as the proxy for latent engineering need. Do not present the former as direct ground truth for the latter; where richer maintenance records are unavailable, report the policy/scheduling limitation in every model result.
