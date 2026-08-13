"""Script to construct and execute notebooks/model_dataset_eda_v1_1.ipynb with full V1.1 EDA,
Model Evaluation (v1.0 vs v1.1), Feature Importance, Ablation, and Shed Error Analysis.
"""
import sys
from pathlib import Path
import nbformat as nbf

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def build_notebook():
    nb = nbf.v4.new_notebook()
    nb.cells = []

    # Title
    nb.cells.append(nbf.v4.new_markdown_cell("""# Model Dataset v1.1 — Physics-Informed EDA, Model Evaluation & Error Diagnostics

**Date:** 2026-08-04  
**Dataset:** `model_datasets/v1.1/model_dataset_v1.1.parquet` (202,237 supervised Gold-B intervals)  
**What changed vs v1.0:** added 20 physics features (`phys_*`) + 18 raw measured geometry features at interval end (`geom_*`) — point-in-time safe, existing data only. Domain constants: new diameter 1096 mm, condemning 1016 mm.
**Scope:** EDA of the new feature groups, v1.0 vs v1.1 model comparison, ablation, permutation importance, and residual/shed diagnostics.
"""))

    # Imports & Setup
    nb.cells.append(nbf.v4.new_code_cell("""import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.inspection import permutation_importance
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["figure.dpi"] = 120

PROJECT_ROOT = Path("..").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
MANIFEST_PATH = PROJECT_ROOT / "model_datasets" / "v1.1" / "model_dataset_manifest_v1.1.json"
PHYSICS_PATH = PROJECT_ROOT / "model_datasets" / "physics" / "physics_features_v1.1.parquet"
COMPARISON_PATH = PROJECT_ROOT / "models" / "experiments" / "v1.1" / "comparison.csv"
ABLATION_PATH = PROJECT_ROOT / "models" / "experiments" / "v1.1" / "ablation" / "ablation.csv"
ERROR_DIR = PROJECT_ROOT / "models" / "experiments" / "v1.1" / "error_analysis"

print("Setup completed successfully.")
"""))

    # Section 1: Dataset Overview
    nb.cells.append(nbf.v4.new_markdown_cell("""## 1. Dataset Overview & Augmentation
- **Rows / splits identical to v1.0** (grouped temporal by wheelset median interval-end; no wheelset spans folds).
- **X features:** 98 total = 58 (v1.0) + 20 physics + 18 measured geometry + 2 life-cycle.
- **Validation:** PASS (no NA in X, no label leakage, no wheelset overlap).
"""))

    nb.cells.append(nbf.v4.new_code_cell("""dataset = pd.read_parquet(DATASET_PATH)
manifest = json.loads(MANIFEST_PATH.read_text())

x_cols = [c for c, r in manifest["column_roles"].items() if r == "feature"]
geom_cols = [c for c in x_cols if c.startswith("geom_")]
phys_cols = [c for c in x_cols if c.startswith("phys_")]

summary_df = pd.DataFrame({
    "Interval Count": dataset["split"].value_counts(),
    "Percentage (%)": (dataset["split"].value_counts(normalize=True) * 100).round(2),
    "Unique Wheelsets": dataset.groupby("split")["wheelset_equipment_id"].nunique(),
    "Unique Locomotives": dataset.groupby("split")["locomotive_id"].nunique()
})
display(summary_df)
print(f"\\nX features: {len(x_cols)} = {len(x_cols) - len(geom_cols) - len(phys_cols)} (v1.0) + {len(geom_cols)} geom_ + {len(phys_cols)} phys_")
"""))

    # Section 2: New Feature Group Distributions
    nb.cells.append(nbf.v4.new_markdown_cell("""## 2. New Augmentation Feature Groups

Two families were added, both point-in-time safe (as-of `interval_end_measurement_id`):
- **`geom_*` — raw measured geometry at the prediction timestamp.** Current diameter, root, flange, tread wear, tire thickness, wear rate. These describe the wheel's *absolute physical state* (what a maintenance engineer actually knows), not just how it changed last interval.
- **`phys_*` — engineered physics state.** `remaining_material` (current dia − 1016), `wear_fraction` (current−1016)/(initial−1016), `material_consumed_pct`, `cumulative_wear`, `interval_wear_rate`, `wear_acceleration`, `ema_wear_rate`, `remaining_budget_days`, `turning_events_cumulative`, `wheelset_age_days`.
"""))

    nb.cells.append(nbf.v4.new_code_cell("""fig, axes = plt.subplots(2, 3, figsize=(16, 8))

# Measured diameter at interval end (the key new signal)
sns.histplot(dataset["geom_wsmDia1"].dropna(), bins=60, kde=True, ax=axes[0, 0], color="#2b5c8f")
axes[0, 0].axvline(1016, color="red", ls="--", lw=1.2, label="condemning 1016")
axes[0, 0].axvline(1096, color="green", ls="--", lw=1.2, label="new 1096")
axes[0, 0].set_title("Measured diameter side 1 (mm)")
axes[0, 0].legend()

# Remaining material (physics Level 1)
sns.histplot(dataset["phys_remaining_material_mm_s1"].dropna(), bins=60, kde=True, ax=axes[0, 1], color="#e6550d")
axes[0, 1].set_title("Remaining material side 1 (mm = dia - 1016)")

# Wear fraction
sns.histplot(dataset["phys_wear_fraction_s1"].dropna(), bins=60, kde=True, ax=axes[0, 2], color="#31a354")
axes[0, 2].set_title("Wear fraction remaining side 1 (0..1)")

# Tire thickness
sns.histplot(dataset["geom_wsmTireThikness1"].dropna(), bins=50, kde=True, ax=axes[1, 0], color="#756bb1")
axes[1, 0].set_title("Tire thickness side 1 (mm)")

# Cumulative wear
sns.histplot(dataset["phys_cumulative_wear_mm_s1"].dropna(), bins=60, kde=True, ax=axes[1, 1], color="#2ca25f")
axes[1, 1].set_title("Cumulative wear side 1 (mm)")

# EMA wear rate
sns.histplot(dataset["phys_ema_wear_rate_s1"].dropna(), bins=60, kde=True, ax=axes[1, 2], color="#dd3497")
axes[1, 2].set_title("EMA wear rate side 1 (mm/day)")

plt.tight_layout()
plt.show()
"""))

    # Section 3: Feature-Label Correlation
    nb.cells.append(nbf.v4.new_markdown_cell("""## 3. Correlation with the Regression Target

The central hypothesis of V1.1: **absolute measured geometry at interval end is the highest-value predictor**. Verify directly against the regression label `next_interval_dia_delta_mm`.
"""))

    nb.cells.append(nbf.v4.new_code_cell("""label = "next_interval_dia_delta_mm"
corr = dataset[x_cols].apply(lambda s: s.corr(dataset[label])).abs().sort_values(ascending=False)
print("Top 15 |correlation| with next-interval diameter delta:")
print(corr.head(15).to_string())

fig, ax = plt.subplots(figsize=(9, 6))
sns.barplot(x=corr.head(15).values, y=corr.head(15).index, ax=ax, palette="viridis")
ax.set_title("|Correlation| with next_interval_dia_delta_mm")
ax.set_xlabel("|Pearson r|")
plt.tight_layout()
plt.show()
"""))

    # Section 4: Model Performance v1.0 vs v1.1
    nb.cells.append(nbf.v4.new_markdown_cell("""## 4. Model Performance — v1.0 vs v1.1 (identical split/labels)

Same 4-5 models, same grouped temporal split, only the feature set changed. TEST split.
"""))

    nb.cells.append(nbf.v4.new_code_cell("""comparison = pd.read_csv(COMPARISON_PATH)
test_comp = comparison[comparison["split"] == "test"].copy()

print("=== REGRESSION (RMSE, lower is better) ===")
reg = test_comp[test_comp["task"] == "regression"]
display(reg.pivot_table(index="model", columns="feature_set", values="rmse").sort_values("v1.1"))

print("\\n=== BINARY LARGE LOSS (PR-AUC, higher is better) ===")
loss = test_comp[(test_comp["task"] == "binary") & (test_comp["label"] == "next_interval_large_loss_flag")]
display(loss.pivot_table(index="model", columns="feature_set", values="pr_auc").sort_values("v1.1"))

print("\\n=== BINARY TURNING (PR-AUC) ===")
turn = test_comp[(test_comp["task"] == "binary") & (test_comp["label"] == "next_interval_turning_flag")]
display(turn.pivot_table(index="model", columns="feature_set", values="pr_auc").sort_values("v1.1"))

print("\\n=== SURVIVAL (C-index) ===")
surv = test_comp[test_comp["task"] == "survival"]
display(surv.pivot_table(index="model", columns="feature_set", values="c_index").sort_values("v1.1"))
"""))

    nb.cells.append(nbf.v4.new_code_cell("""fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# 1. Regression RMSE by feature set
reg_wide = reg.pivot_table(index="model", columns="feature_set", values="rmse").reindex(["v1.0", "v1.1"])
reg_wide.plot.bar(ax=axes[0], color=["#9ecae1", "#3182bd"])
axes[0].set_title("Regression: Test RMSE (mm) ↓")
axes[0].set_ylabel("RMSE (mm)")
axes[0].legend(title="feature set")

# 2. Large-loss PR-AUC by feature set
loss_wide = loss.pivot_table(index="model", columns="feature_set", values="pr_auc").reindex(["v1.0", "v1.1"])
loss_wide.plot.bar(ax=axes[1], color=["#c6dbef", "#08519c"])
axes[1].set_title("Binary Large Loss: Test PR-AUC ↑")
axes[1].set_ylabel("PR-AUC")
axes[1].legend(title="feature set")

# 3. Survival C-index by feature set
surv_wide = surv.pivot_table(index="model", columns="feature_set", values="c_index").reindex(["v1.0", "v1.1"])
surv_wide.plot.bar(ax=axes[2], color=["#c7e9c0", "#31a354"])
axes[2].set_title("Survival: Test C-index ↑")
axes[2].set_ylabel("C-index")
axes[2].legend(title="feature set")

plt.tight_layout()
plt.show()
"""))

    # Section 5: Ablation
    nb.cells.append(nbf.v4.new_markdown_cell("""## 5. Ablation — Measured Geometry vs Engineered Physics

Is the gain from exposing the raw geometry, or from the engineered physics features? HGB, test split.
"""))

    nb.cells.append(nbf.v4.new_code_cell("""ablation = pd.read_csv(ABLATION_PATH)
display(ablation.to_string(index=False))

fig, axes = plt.subplots(1, 2, figsize=(15, 5))

# Regression
ab_reg = ablation[ablation["label"] == "next_interval_dia_delta_mm"]
sns.barplot(data=ab_reg, x="variant", y="rmse", ax=axes[0], order=["v1_0", "plus_geom", "plus_phys", "plus_all"], palette="Reds_d")
axes[0].set_title("Regression RMSE by feature subset")
axes[0].set_ylabel("RMSE (mm)")

# Large loss
ab_loss = ablation[ablation["label"] == "next_interval_large_loss_flag"]
sns.barplot(data=ab_loss, x="variant", y="pr_auc", ax=axes[1], order=["v1_0", "plus_geom", "plus_phys", "plus_all"], palette="Blues_d")
axes[1].set_title("Large Loss PR-AUC by feature subset")
axes[1].set_ylabel("PR-AUC")

plt.tight_layout()
plt.show()
"""))

    nb.cells.append(nbf.v4.new_markdown_cell("""### Ablation takeaway
- **`+geom` (raw measured geometry alone):** RMSE 23.10 → 15.65, PR-AUC 0.845 → 0.928 — the single largest jump.
- **`+phys` (engineered physics alone):** RMSE → 16.50 — strong but smaller.
- **`+all`:** 15.70 / 0.927 — combining adds little beyond geometry.

**Conclusion:** the win comes primarily from *exposing the absolute measured wheel state* at prediction time, not from hand-engineered physics. This is the highest-value, lowest-effort feature addition in the project so far.
"""))

    # Section 6: Permutation Importance
    nb.cells.append(nbf.v4.new_markdown_cell("""## 6. Permutation Importance (HGB, v1.1, test)

Which features drive predictions in the v1.1 model?
"""))

    nb.cells.append(nbf.v4.new_code_cell("""train_df = pd.read_parquet(PROJECT_ROOT / "model_datasets" / "v1.1" / "train_v1.1.parquet")
test_df = pd.read_parquet(PROJECT_ROOT / "model_datasets" / "v1.1" / "test_v1.1.parquet")
sample_test = test_df.sample(min(4000, len(test_df)), random_state=42)

# Regression
hgb_reg = HistGradientBoostingRegressor(max_iter=150, random_state=42).fit(train_df[x_cols], train_df["next_interval_dia_delta_mm"])
p_reg = permutation_importance(hgb_reg, sample_test[x_cols], sample_test["next_interval_dia_delta_mm"], n_repeats=4, random_state=42, n_jobs=-1)
imp_reg = pd.Series(p_reg.importances_mean, index=x_cols).sort_values(ascending=False)

# Large loss
hgb_loss = HistGradientBoostingClassifier(max_iter=150, random_state=42).fit(train_df[x_cols], train_df["next_interval_large_loss_flag"])
p_loss = permutation_importance(hgb_loss, sample_test[x_cols], sample_test["next_interval_large_loss_flag"], scoring="average_precision", n_repeats=4, random_state=42, n_jobs=-1)
imp_loss = pd.Series(p_loss.importances_mean, index=x_cols).sort_values(ascending=False)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
sns.barplot(x=imp_reg.head(12).values, y=imp_reg.head(12).index, ax=axes[0], palette="viridis")
axes[0].set_title("Top 12: Regression (RMSE drop)")
axes[0].set_xlabel("Permutation importance")

sns.barplot(x=imp_loss.head(12).values, y=imp_loss.head(12).index, ax=axes[1], palette="plasma")
axes[1].set_title("Top 12: Large Loss (PR-AUC drop)")
axes[1].set_xlabel("Permutation importance")

plt.tight_layout()
plt.show()
"""))

    nb.cells.append(nbf.v4.new_markdown_cell("""### Feature attribution summary
- `phys_remaining_material_mm_s1/s2` (remaining material = dia − 1016) dominate regression, ~2× the next feature.
- `geom_wsmTireThikness1/2` (tire thickness) and `diameter_delta_raw_mm_side_1` are the next tier.
- Physics + geometry together replace most of the context features (RTIS, shed, interval length) that mattered in v1.0.

This is exactly the expected behavior: the model now reads the wheel's *current* physical condition directly rather than inferring it from how it changed before.
"""))

    # Section 7: Residual / Shed Error Analysis
    nb.cells.append(nbf.v4.new_markdown_cell("""## 7. Residual & Shed Error Analysis (v1.0 → v1.1)

Did the improvements hold across sheds and operational strata? Read the residual analysis output.
"""))

    nb.cells.append(nbf.v4.new_code_cell("""import pathlib
resid = pd.read_csv(ERROR_DIR / "regression_strata_improvement.csv")

# Shed-level MAE change
shed_rows = resid[resid["feature"] == "home_shed"].sort_values("mae_change_pct").head(12)
fig, ax = plt.subplots(figsize=(9, 6))
sns.barplot(data=shed_rows, x="mae_change_pct", y="value", ax=ax, palette="Reds_d")
ax.set_title("Shed-level MAE change, v1.0 → v1.1 (%)")
ax.set_xlabel("MAE change %")
plt.tight_layout()
plt.show()

display(shed_rows[["value", "n_test", "mae_v1_0", "mae_v1_1", "mae_change_pct", "worst100_share_v1_0", "worst100_share_v1_1"]])
"""))

    nb.cells.append(nbf.v4.new_markdown_cell("""### Residual findings
- MAE improved **30–55% across every shed** (PADX −55%, ETE −48%, GMOE −47%).
- The previously worst shed `PADX` (11× worst-100 enrichment in v1.0) left the worst-100 entirely.
- Remaining worst-100 residuals are dominated by label sentinels (e.g. y_true ≈ +1050 mm) and genuinely surprising intervals, not shed or geometry patterns.
"""))

    # Section 8: Summary & Roadmap
    nb.cells.append(nbf.v4.new_markdown_cell("""## 8. Summary & Roadmap

### V1.1 delivered (existing data only)
1. **Regression RMSE 23.10 → 15.70 (−32%)**, MAE −29%, Spearman 0.35 → 0.64.
2. **Large-loss PR-AUC 0.845 → 0.927** (logistic 0.768 → 0.902).
3. Ablation proves the dominant driver is exposing **absolute measured geometry** at interval end — the wheel's current physical state.
4. Errors improved uniformly across sheds; no shed is a systematic outlier anymore.

### Why this matters for V2.0
The geometry features fixed what geometry can fix. The tasks still flat:
- **Turning (PR-AUC ≈ prevalence)** and **survival (C-index ~0.54)** are duty/loading problems — they need distance (RTIS km), track geometry, and telemetry (curvature, brake energy, contact forces), which geometry alone cannot provide.

### Recommended next steps
1. Rolling-temporal (Protocol B) evaluation on v1.1 to confirm production transfer.
2. Quarantined label spec (v1.1) to strip sentinel regression targets.
3. V2.0 data: RTIS distance/km semantics, track geometry, telemetry → target turning + survival.
"""))

    # Write notebook file
    nb_path = PROJECT_ROOT / "notebooks" / "model_dataset_eda_v1_1.ipynb"
    with open(nb_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"Notebook written to {nb_path}")

if __name__ == "__main__":
    build_notebook()
