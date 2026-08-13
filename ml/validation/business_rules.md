# Business Rules

**Status:** Awaiting engineering validation.

Rules requiring named approval before decision scoring or labels:

- wheel/equipment versus wheelset identity semantics;
- interpretation of `wsmturning1`, `wsmturning2` and replacement fields;
- valid units and limits for diameter, flange and gauge;
- acceptable diameter increase after turning/reprofiling;
- definition of intervention/failure endpoints for RUL;
- interpretation of RTIS `RlkdTotalDistance` (cumulative or interval value).

## Engineering Truth Validation

Before creating wear or exposure features, retain evidence for:

- positive-duration intervals and same-locomotive endpoint checks;
- duplicate interval endpoints;
- raw geometry-delta direction/distribution, without prematurely labelling it
  as wear;
- RTIS locomotive/day grain, multiple-division behaviour, non-negativity and
  valid aggregation semantics.
