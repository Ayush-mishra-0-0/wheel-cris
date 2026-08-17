#!/usr/bin/env python
"""Probe WES data for loco 39186 — which wheelsets are current vs historical."""
import pandas as pd
from pathlib import Path

# Load WES (wheel_engineering_state)
wes_path = Path("ml/model_datasets/v3/wheel_engineering_state_v1.0.parquet")
if wes_path.exists():
    wes = pd.read_parquet(wes_path, columns=[
        "wheelset_equipment_id", "LomNumber", "measurement_timestamp", "wsmDia1", "wsmDia2"
    ])
    print("✓ WES loaded")
    print(f"  Shape: {wes.shape}")
    print(f"  Locos: {wes['LomNumber'].nunique()} unique")
    print(f"  Wheelsets: {wes['wheelset_equipment_id'].nunique()} unique")
    print(f"  Date range: {wes['measurement_timestamp'].min()} to {wes['measurement_timestamp'].max()}")
    print()
else:
    print("✗ WES not found")
    exit(1)

# Probe: loco 39186
loco = "39186"
w_39186 = wes[wes["LomNumber"].astype(str) == loco]
print(f"Probe: loco {loco}")
print(f"  A (all historical wheelsets): {w_39186['wheelset_equipment_id'].nunique()}")

# B: latest measurement per wheelset
latest_per_ws = wes.sort_values("measurement_timestamp").groupby("wheelset_equipment_id").tail(1)
b_39186 = latest_per_ws[latest_per_ws["LomNumber"].astype(str) == loco]
print(f"  B (latest meas still on {loco}): {len(b_39186)}")
print(f"    Wheelsets: {sorted(b_39186['wheelset_equipment_id'].unique())}")

# C: within 90d AND on loco
latest_date = wes["measurement_timestamp"].max()
cutoff_90d = pd.Timestamp(latest_date) - pd.Timedelta(days=90)
c_39186 = latest_per_ws[
    (latest_per_ws["LomNumber"].astype(str) == loco) & 
    (latest_per_ws["measurement_timestamp"] >= cutoff_90d)
]
print(f"  C (within 90d AND on {loco}): {len(c_39186)}")

# Show staleness for all A (ever on loco)
print(f"\nStaleness distribution for all {loco} records:")
staleness = (pd.Timestamp(latest_date) - w_39186.groupby("wheelset_equipment_id")["measurement_timestamp"].max()).dt.days
print(staleness.describe())
print("\nStaleness by band:")
print(f"  0-90d:    {(staleness <= 90).sum()}")
print(f"  91-180d:  {((staleness > 90) & (staleness <= 180)).sum()}")
print(f"  181-365d: {((staleness > 180) & (staleness <= 365)).sum()}")
print(f"  >365d:    {(staleness > 365).sum()}")

# Detail: show the B wheelsets with their latest info
print(f"\n=== Latest state for 'current fit' wheelsets (B) ===")
for ws_id in sorted(b_39186['wheelset_equipment_id'].unique()):
    row = b_39186[b_39186['wheelset_equipment_id'] == ws_id].iloc[0]
    meas_ts = row['measurement_timestamp']
    days_old = (pd.Timestamp(latest_date) - pd.Timestamp(meas_ts)).days
    print(f"WS {ws_id}: {meas_ts} ({days_old}d old) on loco {row['LomNumber']}")

# Check if there are assignment tables in the data
print("\n=== Checking for assignment/equipment history tables ===")
bronze_path = Path("ml/data/bronze")
gold_path = Path("ml/data/gold")
for p in [bronze_path, gold_path]:
    if p.exists():
        tables = list(p.glob("*.parquet"))
        relevant = [t for t in tables if "assign" in t.name.lower() or "equip" in t.name.lower()]
        if relevant:
            print(f"  {p.name}: {[t.name for t in relevant]}")
        else:
            print(f"  {p.name}: (no assignment/equipment tables found)")
