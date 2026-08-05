# Distance recovery (station-pair + loco-run distances from open data)

Experimental distance feature source to break the regression RMSE plateau
(14-16, R² 0.53-0.55). Turns the **FOIS loco track-history** into per-loco
daily movement distances by map-matching station sequences against an open
Indian rail network.

> **EXPERIMENTAL_NOT_RELEASED.** Distances here are estimates from an open,
> simplified network. They are **not** authoritative chainage and must not be
> shipped as production features without a versioned cross-check (timetable km).

## Data sources

| Source | Use | License |
| --- | --- | --- |
| Station reference (gist geojson, 8.7k points) | station code -> lat/lon | community/public domain — verify before production |
| Rail network (gist geojson, ~2k lines) | along-network distance base | community/public domain — verify before production |
| OSM rail export (HDX, optional `--osm`) | higher-fidelity upgrade path | ODbL |
| Timetable schedules (2,858 trains, CC0) | **validation** ground-truth for station-pair km | CC0-1.0 |

All registered in `configs/sources.json` with per-source caveats; nothing here is
official IR chainage.

## Pipeline

```text
01_fetch_sources.py     download/cache geojson + schedules      (idempotent, --osm/--force)
02_build_reference.py   -> data/processed/*.parquet             stations, rail_edges,
                                                                 timetable_stations,
                                                                 validation_pairs
03_compute_distances.py -> station_matches.parquet              snap station codes to rail
                        -> pair_distances.parquet               geo_km / rail_km per pair
                        -> reports/distance_validation*.md/.png vs timetable ground-truth
04_map_match_track_history.py                                   FOIS station sequences ->
                        -> fois_transition_distances.parquet    per-loco transition km
                        -> fois_loco_daily_distance.parquet     per-loco per-day rail+geo km
                        -> reports/fois_mapping_report.md
05_validate_rtis_vs_fois.py                                    RTIS movement vs FOIS reports:
                        -> reports/rtis_fois_crosscheck_*.md    row-level division/station/geo
                                                                 agreement + loco-day sequence
                                                                 agreement (division-sequence test)
06_three_way_distance_validation.py                            three independent sources agree?
                        -> reports/three_way_distance_validation.md
                                                                 timetable km vs map-matched vs
                                                                 RTIS distance (auto-uses the
                                                                 safe table from 07 when present)
07_safe_rtis_daily_aggregation.py                             multi-division km + double-data rejection
                        -> data/processed/rtis_daily_safe.parquet   dedup + cap + per-division-cap
                        -> data/processed/rtis_daily_candidate.parquet (with outlier flags, for 08)
                        -> reports/rtis_safe_aggregation_report.md  outliers (<0.3%) rejected
08_adjudicate_rtis_outliers.py                             FOIS adjudicates the RTIS outliers:
                        -> data/processed/rtis_daily_adjudicated.parquet
                        -> reports/rtis_outlier_adjudication_report.md
                                                                 ratio rtis/recon -> DOUBLE /
                                                                 UNDER / REAL / PARTIAL / UNRESOLVED
```

FOIS extract: see `sql/extract_fois_trackhistory.sql`, save as
`data/fois_trackhistory_wap7.parquet`. When absent, the mapper runs in
**sample mode** with a synthetic WAP7 route so the pipeline is testable.
RTIS/FOIS pairing: `sql/extract_rtis_fois_crosscheck.sql` → `data/rtis_fois_paired.parquet`.

## Distance semantics

- `geo_km` — haversine great-circle distance (strict **lower bound**, cuts
  curves/junctions).
- `rail_km` — along-the-line distance when **both** stations snap to the same
  rail edge: `|along_A - along_B|` (only within one polyline; no multi-edge
  routing yet).
- Pairs on different lines / yards / halts → `rail_km` is `None` and flagged
  (`same_edge=False`), never invented.

## Validation status (REAL production run, 2026-08)

Full pipeline executed on the real WAP7 extract: **15,574,443 FOIS track-history
rows** (2025-10-27 → 2026-06-10, 2,272 locos) pulled directly from
`view_locolocation_trackhistory` (see `scripts/extract_fois_trackhistory.py`,
creds in `.env`), map-matched, and cross-checked against RTIS + timetable.

- **Pair-level vs timetable** (864,675 consecutive station-pairs, 2,858 trains):
  same-edge `rail_km` median |%error| **1.79%**, 88.1% within 10%, Spearman
  0.989. This validates the distance CALCULATION wherever coverage exists.
- **Safe multi-division RTIS aggregation** (4.32M rows): exact business-key
  dedupe removes 153,221 re-ingested rows; combined outlier rule flags **0.29%**
  of loco-days → **1,325,675 safe loco-days (99.7%)**, max 3,292 km/day.
- **Outlier adjudication via FOIS** (`08`): of 3,880 RTIS outliers, the FOIS
  reconstruction **confirmed 80 as double-counted** (replaced by FOIS recon),
  18 PARTIAL, 3,782 UNRESOLVED (outside FOIS coverage window — excluded, never
  zeroed).
- **Daily FOIS-recon vs RTIS-safe** (31,073 real overlap days, 27,586 active):
  median RTIS/recon ratio 2.32 — FOIS recon is a **coverage-limited lower bound**
  (21% of FOIS stations not geocoded → ~10% of hops 0; geo fallback is
  great-circle; FOIS misses intra-yard/multi-trip movement), NOT an accuracy
  error. Production daily distance = **RTIS-safe primary, FOIS recon as route
  check + fallback**.
- **Shed movement**: 11.2% of overlap days < 20 km (shed-internal / stabling),
  kept out of distance metrics (corroborated by FOIS shed in/out records).
- Coverage caveat: 79.5% of real FOIS station codes geocode to the open
  reference; the remaining 20.5% are halts/non-standard codes.

## Production run (whole FOIS history)

```powershell
# 1. Extract the FULL track history from SQL Server (see sql/extract_fois_trackhistory.sql,
#    Variant A or A1 for 2016-2026) into data/fois_trackhistory_wap7.parquet
#    (~88M rows for all loco types; chunk the export if needed).

# 2. Fetch sources once + build reference + pair-level validation
.ayush\Scripts\python.exe distance_recovery\scripts\01_fetch_sources.py
.ayush\Scripts\python.exe distance_recovery\scripts\02_build_reference.py
.ayush\Scripts\python.exe distance_recovery\scripts\03_compute_distances.py --validate

# 3. Smoke test on a slice before the full run (optional)
.ayush\Scripts\python.exe distance_recovery\scripts\04_map_match_track_history.py --track-history data\fois_trackhistory_wap7.parquet --limit 500000

# 4. Full run: map-match every loco -> transitions + per-loco daily distance
.ayush\Scripts\python.exe distance_recovery\scripts\04_map_match_track_history.py --track-history data\fois_trackhistory_wap7.parquet

# 5. RTIS/FOIS paired cross-validation (from FOIS_LocoLocation_History, see
#    sql/extract_rtis_fois_crosscheck.sql) -> data/rtis_fois_paired.parquet
.ayush\Scripts\python.exe distance_recovery\scripts\05_validate_rtis_vs_fois.py --paired data\rtis_fois_paired.parquet

# 6. Safe multi-division RTIS daily distance (real data, ~4M rows)
.ayush\Scripts\python.exe distance_recovery\scripts\07_safe_rtis_daily_aggregation.py

# 7. Adjudicate the RTIS outlier days with the FOIS reconstruction as witness
.ayush\Scripts\python.exe distance_recovery\scripts\08_adjudicate_rtis_outliers.py --fois-daily data\processed\fois_loco_daily_distance.parquet

# 8. Three-way validation on the FULL FOIS daily ledger
.ayush\Scripts\python.exe distance_recovery\scripts\06_three_way_distance_validation.py --fois-daily data\processed\fois_loco_daily_distance.parquet
```

Full 88M-row mapper is vectorised (O(n) pandas ops); expect ~5-20 min plus a
few GB RAM depending on the extract size.

## Known limitations

1. Single-edge snapping only — no shortest-path routing across the network, so
   two stations on the same route but split across edges are unmatched.
2. VMAP/OSM network is simplified; absolute km is an estimate (coarse vertices).
3. Station geocodes are community-maintained — code typos land on `matched=False`.
4. Timetable km is cumulative schedule distance, a useful cross-check but not
   identical to track-chart chainage.

## Next steps

- Upgrade the matcher to the HDX OSM network (`01_fetch_sources.py --osm`).
- Add multi-edge routing (grid-index Dijkstra) to close the `same_edge=False` gap.
- Emit `daily_distance_km` candidate feature and re-run the v1.2 model
  (+experimental flag) to measure RMSE delta.
