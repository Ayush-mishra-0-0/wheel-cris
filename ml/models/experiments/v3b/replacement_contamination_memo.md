# Replacement-Contamination Memo — Phase 3C Stage B (diagnostic only)

> **Status: memo only.** This is a diagnostic ablation, **not** a benchmark and
> **not** a Phase 3C result. It does not change any released model or dataset.

## 1. Question

How much of the 17.95 mm diameter MAE reported in the v3b next-state model
(`models/experiments/v3b/degradation_results.json`) is lifecycle
(replacement) contamination — i.e. training pairs that span a wheel
replacement and therefore teach the model a reset, not wear?

## 2. Method

| Item | Value |
| --- | --- |
| Cohort | Frozen rows of `model_datasets/v3b/degradation_pairs.parquet` (252,183 pairs) |
| Wear pairs (both arms) | `crosses_reset == False` → 243,373; drop `next_record_id` NA → 243,373 |
| Split | Chronological 80/20, identical **test** indices for both arms |
| Experiment A | Old v3b training rows (turning-only `crosses_reset` exclusion) → 194,699 |
| Experiment B | Same rows **minus replacement-boundary pairs** from the Stage A engineering-event ledger → 191,208 (3,491 excluded) |
| Replacement boundary | Pair whose `(measurement_timestamp, next_time]` interval contains a ledger `replacement` event for the same wheelset, strictly between current and next measurement (`lo < evt <= hi`) |
| Model | Identical to `run_degradation_model.py`: Ridge(α=10) + RF(250, depth 14, leaf 15), same features, seed 42 |
| Test set | 48,674 pairs, incl. 198 replacement-boundary pairs (held in test in both arms) |

Reproducible via `models/phase3b/replacement_contamination_ablation.py`; JSON in
`replacement_contamination_results.json`.

## 3. Finding — the 17.95 mm baseline is partly a pipeline artifact

While replicating Experiment A we found the stored baseline is affected by a
**feature/target misalignment** in `run_degradation_model.py`: `Y`/`B` are
computed on the parquet (wheelset-grouped) row order (lines 102-103) but indexed
with positions derived **after** sorting by `measurement_timestamp` (lines 105-108,
121-122), while `X` is indexed after the same sort. The test targets therefore
do not line up with the test features. The ablation therefore reports **two
pairs of arms**:

- **Faithful replication** — reproduces the stored pipeline exactly. Experiment A
  lands on `wsmDia MAE = 17.9511`, matching the stored 17.95.
- **Correctly aligned** — `Y`/`B` computed in the same sorted order as `X`. This
  is the sound pipeline on which the true contamination effect can be read.

## 4. Results

### 4.1 Faithful replication (reproduces the stored baseline)

| Dimension | A MAE | B MAE | Δ MAE | Attrib. fraction | Persist MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| wsmDia | 17.9511 | 17.9588 | −0.008 | ~0.000 | 1.8383 |
| wsmFlangeThickness | 1.0209 | 1.0214 | −0.001 | −0.001 | 0.2640 |
| wsmRoot | 0.8042 | 0.8042 | 0.000 | 0.000 | 0.6863 |
| wsmWheelGauge | 0.3319 | 0.3315 | +0.000 | +0.001 | 0.0797 |

Excluding replacement-boundary pairs changes the documented 17.95 mm MAE by
**< 0.01 mm**. Under the misaligned pipeline the estimation error dominates and
the contamination signal is invisible.

### 4.2 Correctly aligned (sound pipeline)

| Dimension | A MAE | B MAE | Δ MAE | Attrib. fraction | Persist MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| wsmDia | 4.5212 | 4.1412 | +0.3800 | **8.4 %** | 1.9992 |
| wsmFlangeThickness | 1.0820 | 1.0937 | −0.0117 | −1.1 % | 0.2328 |
| wsmRoot | 0.7465 | 0.7477 | −0.0012 | −0.2 % | 0.6379 |
| wsmWheelGauge | 0.2793 | 0.2807 | −0.0014 | −0.5 % | 0.1063 |

On a correctly aligned pipeline the diameter MAE is **4.52 mm**, of which
**0.38 mm (8.4%)** is attributable to replacement contamination in the training
rows. The other three dimensions are unaffected (fraction ~0 or slightly
negative). RF mirrors the same direction (wsmDia 3.19 → 3.11 mm).

## 5. Interpretation

1. **Replacement contamination is a small, real contributor — not the story.**
   On a sound pipeline, lifecycle (replacement) boundary pairs account for
   ~0.38 mm of a 4.52 mm diameter MAE (8.4%). Leaving them in is not the
   dominant source of next-state error.
2. **The documented 17.95 mm figure is inflated by an alignment bug in the v3b
   runner**, not by lifecycle contamination. The honest next-state MAE is
   ~4.5 mm. This does **not** invalidate Phase 3B's *product* (the
   degradation-pairs dataset is unaffected — the bug is in the training
   script's indexing), but the headline metric in `degradation_results.json`
   should be re-derived with aligned targets.
3. **Recommendation** (Phase 3C): in Stage C's segment-aware substrate, keep the
   replacement-boundary exclusion (it is cheap and correct), but do **not** rely
   on it to close the diameter MAE gap. The bigger lever is target alignment and
   the segment-aware features (days-in-segment, distance-since-replacement) that
   the ledger now makes possible.
4. **Exclusion counts**: 3,491 training pairs excluded (1.8 % of Experiment A's
   training rows); 198 replacement-boundary pairs remain in test in both arms, so
   the two arms are compared on identical test data as the plan requires.

## 6. Files

- `models/phase3b/replacement_contamination_ablation.py` — reproducible ablation.
- `models/experiments/v3b/replacement_contamination_results.json` — full per-dimension JSON.
- This memo: `models/experiments/v3b/replacement_contamination_memo.md`.

## 7. Decision recorded

| Decision | Value |
| --- | --- |
| Stage B output | memo only; **not** consumed as a Phase 3C result |
| Replacement exclusion in Stage C | keep (cheap, correct) |
| 17.95 mm headline | flag for re-derivation with aligned targets before it is quoted again |
