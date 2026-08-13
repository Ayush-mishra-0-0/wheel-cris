# RTIS vs FOIS cross-validation — sample

## Row-level agreement (each paired report)

- rows evaluated: 180
- division equality (RTISDvsn == FOISDvsn): 100.0%  (180)
- station equality (RTISSttn == FOISSttn): 90.6%  (163)
- RTIS-coords vs FOIS-station geo distance: median 0.0 km
- geo-plausible within 25.0 km: 100.0%  (evaluable 180)

## Loco-day sequence agreement (both feeds report that day)

- **division sequence** (10 loco-days): identical order 100.0%  (10)
  - days with >=2 distinct divisions in both feeds: 10 → agreement 100.0%
- **station sequence** (10 loco-days): identical order 20.0%  (2)
  - days with >=2 distinct stations in both feeds: 10 → agreement 20.0%

## RTIS feed internal plausibility (no FOIS needed)

- rows: 4,320,461 · loco-days: 1,329,555
- avg distinct divisions / loco-day: 3.06 (max 45)
- loco-days with a single division: 24.1%
- loco-days with >4 distinct divisions: 20.5%
- loco-days using only known division codes: 6.8%

## Interpretation

- High division/station equality + high loco-day sequence agreement is
  independent evidence (FOIS is a separate reporting system) that RTIS
  divisions follow real operational movement.
- Geo check validates RTIS coordinates against FOIS station locations,
  so a GPS glitch cannot masquerade as a division move.
- Sequence agreement is order-exact: it also detects shuffled/duplicated
  report artifacts, not just wrong codes.
