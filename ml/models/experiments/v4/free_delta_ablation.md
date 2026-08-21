# Free-Delta Ablation + Calibration Comparison (2026-08-21)

Artifact: `free_delta_ablation.json` (this directory). Protocol identical to the
committed Phase-4 benchmarks: frozen `v4/risk_benchmark.parquet` anchors/labels,
B1 `LogisticRegression(C=0.1, max_iter=1000, seed=42)` on StandardScaler, same
metric functions. Delta block joined by `measurement_record_id` (100% coverage;
224,697/239,684 anchors have a prior measurement — the rest carry NaN deltas).

## Result: free deltas do NOT materially move Target B ranking

| eval | H | base cap@10 | +Δ cap@10 | Δ | base ROC | +Δ ROC |
|---|---|---|---|---|---|---|
| frozen test | 30d | 0.640 | 0.656 | **+0.016** | 0.872 | 0.872 |
| frozen test | 90d | 0.657 | 0.652 | −0.005 | 0.833 | 0.832 |
| frozen test | 180d | 0.374 | 0.372 | −0.003 | 0.760 | 0.758 |
| never-seen loco | 30d | 0.700 | 0.705 | +0.004 | 0.904 | 0.905 |
| never-seen loco | 90d | 0.725 | 0.739 | **+0.015** | 0.913 | 0.917 |
| never-seen loco | 180d | 0.677 | 0.677 | 0.000 | 0.898 | 0.899 |

Only consistent gain: never-seen-loco 90d (+1.5pp capture@10). Frozen-test 90d
is slightly negative. This is noise-level, not a step change.

**Decision:** keep free deltas out of the serving feature set on this evidence.
They remain materialized (`model_datasets/v5/free_delta_features_v1.parquet`)
for the post-signoff v1.1 benchmark rebuild, where they can be re-tested once
on current data. No re-run before then.

Target A (root) movements are ±0.03 capture@10 with mixed ROC signs — still
noise-level at 0.09–0.2% prevalence; quarantine unchanged.

## Calibration: decile band vs isotonic (Target B, test split)

| H | decile ECE | isotonic ECE | decile Brier | isotonic Brier |
|---|---|---|---|---|
| 30d | 0.0023 | 0.0025 | 0.0046 | 0.0045 |
| 90d | 0.0108 | 0.0107 | 0.0186 | 0.0178 |
| 180d | 0.1122 | **0.0965** | 0.1219 | **0.1140** |

Served horizons are 30/60/90d where the production decile band is already
at parity. Isotonic only wins at 180d (unserved). **Decision:** no calibration
change; revisit only if a 180d horizon is ever served.
