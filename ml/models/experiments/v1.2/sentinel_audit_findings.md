# V1.2 Label Cleanup — Sentinel Audit (Step 1 findings)

**Input:** immutable `model_datasets/v1.1/model_dataset_v1.1.parquet` (202,237 supervised rows) +
bronze `wheel_measurements.parquet`. Label audited:
`next_interval_dia_delta_mm` = `wsmDia1[next_interval_end_measurement_id]` − `wsmDia1[interval_end_measurement_id]`.

## 1. Raw label sanity by split

| split | n | min | max | p99 | p999 | \|Δ\|>100 | \|Δ\|>50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 144,428 | −1090.0 | +1095.0 | 66.9 | 75.2 | 53 | 15,012 |
| val | 29,743 | −214.0 | +1068.4 | 55.0 | 69.0 | 9 | 1,357 |
| test | 28,066 | −77.7 | +1050.5 | 50.5 | 64.6 | 1 | 959 |

~99.9% of labels lie within ±75 mm. The outliers are the classic sentinel tail
(the test split carries exactly **1** row >100 mm: the +1050.5 known from the
visualization suite).

## 2. Two candidate rules

**Rule A — label magnitude:** quarantine rows with `|next_interval_dia_delta_mm| > 100`.

**Rule B — physical endpoint diameter:** quarantine rows where either label-endpoint
measurement (`interval_end_measurement_id` or `next_interval_end_measurement_id`) has
`wsmDia1` outside a physically-plausible wheel-diameter window. Domain constants
(owner-provided): condemning **1016 mm**, new **1096 mm**. Tolerance for measurement
noise and wheels in service near the condemning limit → window **[1000, 1100] mm**.
(The earlier EDA used [600,1300]; that is far too loose — it admits +1280 mm and
0 mm endpoints and misses wheels below condemning, e.g. 962 mm.)

## 3. Result: Rule B subsumes Rule A (100%)

| set | n | train | val | test |
| --- | ---: | ---: | ---: | ---: |
| Rule B ([1000,1100] endpoint wsmDia1) | **65** | 55 | 9 | 1 |
| Rule A (\|Δ\|>100) | 63 | 53 | 9 | 1 |
| A ∩ B | 63 | — | — | — |
| A only (phys-plausible but absurd label) | **0** | — | — | — |
| B only (small label, impossible endpoint) | 2 | — | — | — |

- **Every** |Δ|>100 row (63) also violates the physical window → Rule B has 100%
  recall on Rule A and needs no separate magnitude threshold.
- Rule B additionally catches 2 rows that Rule A misses (labels +61.0, +91.4)
  whose endpoints are non-physical (e.g. start dia 962 mm < condemning 1016).
- After Rule B: max |Δ| among retained rows is **80.3 mm**; retained endpoint
  diameters lie in **[1011.5, 1100.0] mm** — fully physical.

## 4. Why the sentinels matter (RMSE inflation)

On the full 202,237-row label: overall label RMSE = **33.06 mm**.
Excluding the \|Δ|>100 rows → **27.59 mm** (the 63 sentinels carry ~30% of total MSE).
The 59 worst are endpoint-garbage measurements (wsmDia1 as low as 0, as high as
1,020,352 mm in bronze). They poison the **training** target distribution even
though only 1 appears in the test split.

## 5. Recommended V1.2 quarantine rule

> Quarantine a supervised row if `wsmDia1` of `interval_end_measurement_id`
> **or** `next_interval_end_measurement_id` is outside **[1000, 1100] mm**.

- **Rows removed:** 65 / 202,237 (0.03%) — train 55, val 9, test 1. Data loss is negligible.
- Splits remain almost identical; test set becomes 28,065 rows (a 1-row change),
  so the v1.1→v1.2 comparison stays a clean same-split, same-rows comparison.
- Rule is deterministic, domain-grounded (1016/1096 ± tolerance), and reproducible
  from bronze + the two measurement-id columns already in the dataset.
- Side-2 (`wsmDia2`) is **not** part of the regression label (side-1 only), so the
  rule uses wsmDia1; a future rule could extend to wsmDia2/root for the binary/survival
  labels.

## Artifacts

- `sentinel_audit.json` — full audit payload (per-split stats, thresholds cross-tab, RMSE sensitivity).
- `sentinel_audit_thresholds.csv` — Rule A thresholds vs Rule B overlap table.
- `sentinel_rows_gt100.csv` — the 63 |Δ|>100 rows with split/endpoint ids.
