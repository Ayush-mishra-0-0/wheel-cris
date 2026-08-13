# Continuous Evolution & Versioning Guide (v1.0)

This document defines the operational rules for evolving the Wheel Health ML system as new measurements, locomotive cohorts, or RTIS data arrive.

---

## 1. Core Immutability Directives

1. **Never Overwrite Historical Releases:**
   - Any released feature store artifact (`feature_store_vX.Y.parquet`), feature spec (`engineering_feature_specification_vX.json`), label spec (`label_specification_vX.json`), or model dataset (`model_datasets/vX.Y/`) is **immutable**.
   - Experiments in `models/experiments/<version>/` (e.g. `models/experiments/v1.0/`) are read-only once written and auto-increment per task within that version root.

2. **Decoupled Contracts:**
   - **Feature Store Versioning** (`v1.0.0`) is independent of **Model Dataset Versioning** (`v1.0.0`).
   - A single feature store release can back multiple model dataset releases (e.g. if new label horizons or filtering rules are introduced).

---

## 2. Version Bump Taxonomy

| Component | Semantic Bump | Trigger | Example |
|---|---|---|---|
| **Feature Spec** | Patch (`v1.0.1`) | Doc/type clarification, non-breaking fix | `expected_missing_pct` calibration |
| | Minor (`v1.1.0`) | New point-in-time safe feature added | Adding `turning_count_cumulative` |
| | Major (`v2.0.0`) | Feature semantics change or removed | Changing diameter calculation logic |
| **Label Spec** | Patch (`v1.0.1`) | Sentinel outlier quarantine rule fix | Quarantining `wsmDia1 < 600mm` in next measurement |
| | Minor (`v1.1.0`) | New label horizon or target added | Adding `next_interval_wear_rate_mm_per_day` |
| | Major (`v2.0.0`) | Label event definition altered | Changing turning classification threshold |
| **Model Dataset** | Patch (`v1.0.1`) | Imputation fix, split boundary fix | Bugfix in encoding handling |
| | Minor (`v1.1.0`) | Ingest of new operational data timeframe | Appending Q3/Q4 2026 wheel measurements |
| | Major (`v2.0.0`) | New locomotive cohort expanded | Adding WAP5 / WAG9 locos to WAP7 |

---

## 3. Continuous Iteration Workflow

When new raw inspection or RTIS data is ingested from SQL production:

```
[Raw SQL DB Ingest] 
       │
       ▼
[Silver/Gold Pipeline] ──> Build new Feature Store release (e.g., v1.1.0)
       │
       ▼
[Feature Spec Check]  ──> Verify point-in-time safety & missingness bounds
       │
       ▼
[Eligibility Filter] ──> Run training_eligibility.py -> manifest_v1.1.json
       │
       ▼
[Dataset Builder]    ──> build_model_dataset.py --dataset-version 1.1.0
       │                 Generates: train/val/test_v1.1.parquet, dataset_card.md
       │
       ▼
[Dataset Validation] ──> validate_dataset.py -> MUST return PASS verdict
       │
       ▼
[Data Drift Check]   ──> Compare v1.1.0 vs v1.0.0 feature distributions (PSI / KS-test)
       │
       ▼
[Model Training]     ──> run_baselines.py / run_models.py
                         Writes new auto-incremented experiment_XXXX entries
```

---

## 4. Dataset Drift Detection Protocol

Before training models on a new dataset release `v1.1.0`, compare feature and label distributions against `v1.0.0`:

1. **Numeric Features (Population Stability Index - PSI):**
   - $\text{PSI} < 0.10$: No significant distribution shift (Safe).
   - $0.10 \le \text{PSI} \le 0.25$: Moderate shift (Warning: review feature attribution).
   - $\text{PSI} > 0.25$: Major shift (Action required: investigate data pipeline or recalibrate encoders).

2. **Categorical Features (Frequency Shift):**
   - Flag any new unobserved category levels. One-hot encoders MUST map unknown categories to `__NA__` or frequency bucket.

3. **Label Prevalence Shift:**
   - Monitor `next_interval_turning_flag` positive rate across releases. If rate shifts by $> \pm 0.5\%$, trigger domain review.

---

## 5. Model Promotion & Degradation Guardrails

1. **Evaluation Baseline Comparison:**
   - A candidate model on `v1.1.0` MUST outperform the `v1.0.0` champion model on the identical evaluation metrics contract:
     - **Regression:** Lower RMSE & higher Spearman correlation.
     - **Binary:** Higher PR-AUC & Precision@k (k=1000).
     - **Survival:** Higher Harrell C-index.

2. **Champion/Candidate Registry:**
   - Record active champion experiment ID in `models/champion_manifest.json`.
   - Never replace a production model without passing Phase 4 Error Analysis verification (confirming error distribution is not heavily concentrated in key operational sheds).
