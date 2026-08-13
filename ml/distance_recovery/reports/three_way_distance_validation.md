# Three-way distance validation (timetable vs RTIS vs FOIS)

Evidence: REAL FOIS daily vs REAL RTIS
Source: FOIS daily `distance_recovery\data\processed\fois_loco_daily_distance.parquet` · RTIS `SAFE multi-division (1,325,675 loco-days, outliers rejected by 07)` · shed threshold 20.0 km
Loco-days: 31,073 · shed-internal (<20.0 km): 3,487 (11.2%) · active days: 27,586

Low-distance days are shed-internal / stabling movement (docs/rtis_daily_distance_revalidation.md: 15,540 of 29,229 RTIS low-km blocks overlap FOIS shed in/out records) and are kept separate.

## Pairwise agreement (active days only)

| pair | n | Spearman | median \|%diff\| | within 10% | within 20% |
| --- | ---: | ---: | ---: | ---: | ---: |
| recon vs timetable (FOIS route, ground-truth km) | 0 | None | None% | None% | None% |
| recon vs RTIS (map-matched vs sensor) | 27,586 | 0.741 | 56.95% | 0.5% | 1.7% |
| timetable vs RTIS | 0 | None | None% | None% | None% |

## Three-way agreement

No loco-days had all three legs (timetable km is only defined on days whose transitions are schedule pairs — a minority on real routes). On the 0 days where recon and timetable both exist, within-±20% agreement is 0.0%. The timetable is the pair-level ground truth (median 1.79% error); the daily witness is FOIS-recon vs RTIS above.

## Coverage-bias analysis (why FOIS-recon runs below RTIS)

On 27,586 active days with both legs: median RTIS/recon ratio 2.32, 65.3% of days have RTIS > 2x FOIS recon.

FOIS recon is a LOWER BOUND, not a wrong estimate:
- 21% of FOIS station codes are not in the geocoding reference -> ~10% of hops
  have no distance and contribute 0.
- the geo fallback is great-circle (cuts curves/junctions).
- FOIS only reports station-to-station moves; intra-yard shunting and multi-trip
  days with sparse reporting are missed.

Pair-level map-matching accuracy is validated separately at 1.79% median error
(864k timetable pairs) - the disagreement here is COVERAGE, and RTIS-safe is the
fuller daily ledger. Production daily distance = RTIS-safe (07) primary with
FOIS recon as route check + fallback.