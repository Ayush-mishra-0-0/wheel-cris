# Release evidence pack — generated 2026-08-21T11:34:14.727164+00:00

Scope: current-state evidence for the wheel-forecasting release. Every
section states its own status; pending items are shown as pending.

## 1. Data health / lineage

- WES serving artifact: `wheel_engineering_state_v1.1.parquet` rows=278480 built=2026-08-21T09:51:31.329374+00:00
- Bronze extract: rows=1194416 extracted=2026-08-21T07:12:29.814690+00:00 db=SLAM_PROD_DB_10.05.2022
- Lifecycle: 88345 segments / 47855 turns / 19302 wheelsets
- Fleet snapshot: n=19302 built=2026-08-21T10:16:15.194658+00:00 regen=2026-08-21T11:14:51.644632+00:00
- Snapshot sources: model_datasets\v3\wheel_engineering_state_v1.1.parquet; model_datasets\v5\lifecycle_segments_shed.parquet; model_datasets\v5\wheelset_adaptation.parquet; data\gold\interval_context\v1.0\inspection_interval_context.parquet

## 2. Measurement scope (trip-shed exclusion)

- Status: **DB_VERIFIED_PENDING_DOMAIN_SIGNOFF**
- Excluded FLoc codes: CHZ, DBRG
- Excluded section codes: 11 registered
- DB audit: WAP7 register rows at trip FLocs=0, at trip sections=0 (SLAM_PROD_DB_10.05.2022, 2026-08-21)
- Local excluded-row count: 0 (no trip-shed keys present in current WES cohort)
- **Release gate: domain-owner sign-off still open.**

## 3. Benchmarks (Target B ranking; Target A quarantined)

- Frozen benchmark dataset: 239684 rows, limit_root=6.0 mm (sha 8b0595c03465…)
  - 30d: turn events 1279 (rate 0.00559), root events 60 (rate 0.00026)
  - 90d: turn events 4201 (rate 0.01954), root events 203 (rate 0.00094)
  - 180d: turn events 8772 (rate 0.0469), root events 373 (rate 0.00199)
- Rolling 30-step, turn 90d B1: capture@10 median=0.5329, ROC-AUC median=0.9009 (53 cutoffs)
- Never-seen-loco holdout: 422/2110 locos, 48085 holdout rows
- **v1.1 benchmark rebuild: PENDING** (runs after scope sign-off).

## 4. Free-delta ablation & calibration

- Delta join coverage 100.0% of anchors; conclusion: no material Target-B lift (frozen-test cap@10 -0.5..+1.6pp); deltas stay OUT of serving.
- Basis: frozen v4/WES v1.0 benchmark — reconfirm once on post-signoff v1.1 benchmark.
- Conformal (dia 90d): width 1.974 mm, empirical coverage 0.7584 (nominal 0.80)
- Calibration: decile band at parity with isotonic on served horizons (see free_delta_ablation.md).

## 5. Decision surface (live)

- Ranking: calibrated 90d P(turn), Phase 4 Target B (`ranked_by=pturn_90d_calibrated`)
- Worklist: top-k per shed by the same score (capacity-aware)
- Dispositions: JSONL log with decision-time score context (model_datasets/v5/dispositions/)
- Action ladder: **PENDING_CW_SIGNOFF** — tiers not computed until C&W thresholds arrive
- Distance gate: `interval_distance_km` APPROVED and released to serving (docs/distance_serving_gate.md); coverage caveat ~53% intervals, NaN-native

## 6. Ranked examples (top 5, live snapshot)

| wheelset | loco | shed | cal P(turn) 90d | decile | limiting dim | condemning d |
|---|---|---|---|---|---|---|
| 683074 | 30744 | NA | 0.4529 | 9 | wsmRoot | nan |
| 2941610 | 30512 | WATE | 0.4529 | 9 | wsmThread | nan |
| 665990 | 37339 | NA | 0.4529 | 9 | wsmRoot | nan |
| 683073 | 30744 | NA | 0.4529 | 9 | wsmFlange | nan |
| 261354 | 30598 | NA | 0.4529 | 9 | wsmDia | 132.9 |

## 7. Disposition log sample

- `{"ts_utc": "2026-08-21T10:57:10.336643+00:00", "wheelset_equipment_id": 2196463, "loco_number": "30252", "action": "inspect", "note": null, "context": {"snapsho`

## 8. Known limitations

- Target A (root > 6 mm) quarantined: prevalence too low for classification-grade ranking.
- Survival/time-to-event ≈ chance on properly censored data; 'when' beyond the 180d horizon unknown.
- Distance features partial coverage (~53% of intervals); NaN-native serving.
- Trip-shed scope DB-verified but not domain-signed-off; exclusion currently a no-op for WAP7.
- Action ladder thresholds undefined (C&W).
- v1.1 benchmark + ablation rerun pending sign-off.
