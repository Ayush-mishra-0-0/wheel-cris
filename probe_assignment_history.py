#!/usr/bin/env python
"""Check loco_equipment_history for current fit status."""
import pandas as pd
from pathlib import Path

# Check loco_equipment_history
hist_path = Path("ml/data/bronze/loco_equipment_history.parquet")
if hist_path.exists():
    hist = pd.read_parquet(hist_path)
    print(f"✓ loco_equipment_history loaded")
    print(f"  Columns: {hist.columns.tolist()}")
    print(f"  Shape: {hist.shape}\n")
    
    # Filter to loco 39186
    loco = 39186
    h_loco = hist[hist.get("loco_id", -1) == loco] if "loco_id" in hist.columns else hist[hist.get("LomNumber", -1) == loco] if "LomNumber" in hist.columns else pd.DataFrame()
    
    if h_loco.empty and "loco_equipment_id" in hist.columns:
        # Try different column names
        print("Trying to find loco 39186 by different keys...")
        for col in ["loco_number", "locomotive_id", "loco_num"]:
            if col in hist.columns:
                h_loco = hist[hist[col].astype(str) == str(loco)]
                if not h_loco.empty:
                    print(f"  Found using column: {col}")
                    break
    
    if not h_loco.empty:
        print(f"Records for loco {loco}: {len(h_loco)}")
        print("\nSample rows:")
        print(h_loco.head(10).to_string())
    else:
        print(f"No records found for loco {loco} in this table")
        print("\nFirst few rows of the table:")
        print(hist.head())
else:
    print("✗ loco_equipment_history not found")

# Also check equipment_master_register
master_path = Path("ml/data/bronze/equipment_master_register.parquet")
if master_path.exists():
    print("\n" + "="*60)
    print("Equipment Master Register:")
    master = pd.read_parquet(master_path)
    print(f"  Columns: {master.columns.tolist()}")
    print(f"  Shape: {master.shape}")
else:
    print("✗ equipment_master_register not found")
