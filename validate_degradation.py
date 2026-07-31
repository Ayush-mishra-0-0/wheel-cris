import pandas as pd
import numpy as np
import json

# Read the silver layer data
df = pd.read_parquet("data/silver/wheel_measurements.parquet")
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print()

# Get measurement columns (numeric)
numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
print(f"Numeric columns ({len(numeric_cols)}): {numeric_cols}")

# For each numeric column, compute stats
results = {}

for col in numeric_cols:
    s = df[col]
    total = len(s)
    null_count = s.isna().sum()
    null_pct = null_count / total * 100
    zero_count = (s == 0).sum()
    zero_pct = zero_count / total * 100
    min_val = s.min()
    max_val = s.max()
    mean_val = s.mean()
    
    # Outlier detection using IQR
    Q1 = s.quantile(0.25)
    Q3 = s.quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    outlier_count = ((s < lower_bound) | (s > upper_bound)).sum()
    
    results[col] = {
        'total': int(total),
        'null_count': int(null_count),
        'null_pct': round(null_pct, 4),
        'zero_count': int(zero_count),
        'zero_pct': round(zero_pct, 4),
        'min': float(min_val) if pd.notna(min_val) else None,
        'max': float(max_val) if pd.notna(max_val) else None,
        'mean': float(mean_val) if pd.notna(mean_val) else None,
        'outlier_count': int(outlier_count),
        'Q1': float(Q1) if pd.notna(Q1) else None,
        'Q3': float(Q3) if pd.notna(Q3) else None,
        'IQR': float(IQR) if pd.notna(IQR) else None,
    }

# Save results
with open('validation_stats.json', 'w') as f:
    json.dump(results, f, indent=2)

print("Basic stats computed. Now computing deltas...")

# Compute deltas for measurement fields that have prev/next pairs
# We need to sort by equipment and date to get consecutive measurements
# First, let's identify the key columns
# wsmEquipmentId, wsmUpdatedOn are the identity/timestamp

# Check if we have the right columns
print("\nKey columns present:")
for c in ['wsmEquipmentId', 'wsmUpdatedOn', 'wsmId']:
    if c in df.columns:
        print(f"  {c}: {df[c].dtype}")

# Sort by equipment and date
df_sorted = df.sort_values(['wsmEquipmentId', 'wsmUpdatedOn'])

# For each equipment, compute deltas between consecutive measurements
delta_fields = ['wsmDia1', 'wsmDia2', 'wsmFlange1', 'wsmFlange2', 
                'wsmRoot1', 'wsmRoot2', 'wsmThread1', 'wsmThread2',
                'wsmWheelGauge1', 'wsmWheelGauge2', 
                'wsmFlangeThickness1', 'wsmFlangeThickness2',
                'wsmTireThikness1', 'wsmTireThikness2',
                'wsmAxelDia1', 'wsmAxelDia2']

deltas = {}
for field in delta_fields:
    if field in df_sorted.columns:
        # Compute diff within each equipment group
        diff = df_sorted.groupby('wsmEquipmentId')[field].diff()
        valid = diff.dropna()
        pos = (valid > 0).sum()
        neg = (valid < 0).sum()
        zero = (valid == 0).sum()
        deltas[field] = {
            'count': int(len(valid)),
            'positive': int(pos),
            'negative': int(neg),
            'zero': int(zero),
            'positive_pct': round(pos / len(valid) * 100, 2),
            'negative_pct': round(neg / len(valid) * 100, 2),
            'zero_pct': round(zero / len(valid) * 100, 2),
        }

with open('delta_stats.json', 'w') as f:
    json.dump(deltas, f, indent=2)

print("\nDelta stats computed")
for k, v in deltas.items():
    print(f"  {k}: n={v['count']}, pos={v['positive']} ({v['positive_pct']}%), neg={v['negative']} ({v['negative_pct']}%), zero={v['zero']} ({v['zero_pct']}%)")

print("\nDone!")