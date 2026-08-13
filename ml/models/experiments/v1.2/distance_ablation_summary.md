# V2 distance-x ablation — experimental RTIS interval distance (HGB, v1.2 test)

Eval rows: v1.2 test = 28,065.  Same train rows (144,373) and same
test rows for both feature sets; the ONLY difference is the 3 experimental
distance columns. Released distance feature stays BLOCKED; these are
experimental only, to size whether distance exposure can move predictions.

Deduped-distance coverage: 62.7% of intervals have reports;
median interval distance (when reported) = 12,734 km.

| feature_set | n_features | RMSE | MAE | R² |
| --- | ---: | ---: | ---: | ---: |
| baseline | 96 | 14.566 | 11.397 | 0.530 |
| baseline_plus_distance | 99 | 14.531 | 11.382 | 0.532 |

ΔRMSE -0.24% · ΔMAE -0.13% (negative = distance helps).

## Permutation importance (baseline_plus_distance)

`interval_distance_km_experimental` ranks **#4 of 99 features** (perm-importance
mean 3.69 on neg_MSE), behind only `phys_remaining_material_mm_s1` (182.7),
`geom_wsmTireThikness1` (62.8), `rtis_reporting_coverage_pct` (13.3). The two
coverage columns rank far lower (outside top 30) — the raw distance sum carries
the signal.

## Verdict

The gain is real but small (−0.24% RMSE) because the top physical features
already dominate; the distance signal is information-rich (top-5 rank) yet
largely redundant with what `phys_*`/coverage already encode. This is a
**v2.x experiment worth running** (rolling-eval version would give the honest
production number), not a champion replacement yet — and the data-team nod
should cover: exact-key dedupe (loco+date+division+distance), sum-over-interval
grain, and the missing-report ≠ 0-km coverage denominator.
