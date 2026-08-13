"""Censoring diagnosis - what causes wheel measurement records to end?

Quantifies the composition of the 81.5% of equipment whose LAST measurement is
>30 days before the global extract end (2026-07-24). Three candidate causes:

  1. SYNC_LAG      - last seen within the sync-freeze window (global max - 13d);
                     the extract froze and follow-up was cut mid-cycle.
  2. ACTIVE_AT_END - elapsed since last seen is within ~2x the equipment's own
                     historical inspection cadence; consistent with the wheel
                     still being in service, right-censored at global end.
  3. LIKELY_ENDED  - elapsed since last seen is much longer than its cadence;
                     consistent with withdrawal / removal / no-longer-measured.

The split is used to sharpen the survival-analysis censoring assumption.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BRONZE = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3b" / "censoring_diagnosis"
GLOBAL_END = pd.Timestamp("2026-07-24")  # observed global max measurement
SYNC_LAG_DAYS = 13  # days between global max and "today" (2026-08-07)
CADENCE_FACTOR = 2.0  # elapsed > 2x own cadence => likely ended

df = pd.read_parquet(BRONZE, columns=["wsmEquipmentId", "wsmUpdatedOn"])
df = df.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).copy()
df["t"] = pd.to_datetime(df["wsmUpdatedOn"])
df["wsmEquipmentId"] = df["wsmEquipmentId"].astype(str)

rows = []
for eid, g in df.groupby("wsmEquipmentId"):
    g = g.sort_values("t")
    gaps = g["t"].diff().dropna().dt.days
    last = g["t"].max()
    elapsed = (GLOBAL_END - last).days
    n = len(g)
    if n > 1:
        med_gap = float(gaps.median()) if len(gaps) else np.nan
        p90_gap = float(gaps.quantile(0.9)) if len(gaps) else np.nan
    else:
        med_gap = np.nan
        p90_gap = np.nan
    rows.append(
        {
            "equipment": eid,
            "n_measurements": n,
            "first_seen": g["t"].min(),
            "last_seen": last,
            "elapsed_days": elapsed,
            "median_gap_days": med_gap,
            "p90_gap_days": p90_gap,
        }
    )

tab = pd.DataFrame(rows)

def classify(r):
    if r["elapsed_days"] <= SYNC_LAG_DAYS:
        return "SYNC_LAG"
    if pd.notna(r["median_gap_days"]) and r["median_gap_days"] > 0:
        if r["elapsed_days"] <= CADENCE_FACTOR * r["median_gap_days"]:
            return "ACTIVE_AT_END"
    return "LIKELY_ENDED"

tab["cause"] = tab.apply(classify, axis=1)

summary = tab["cause"].value_counts().to_dict()
tot = len(tab)
summary_pct = {k: round(v / tot * 100, 1) for k, v in summary.items()}

last30_share = float((tab["last_seen"] >= GLOBAL_END - pd.Timedelta(days=30)).mean())
over30 = tab[tab["elapsed_days"] > 30]

reclassified = over30["cause"].value_counts().to_dict()
reclassified_pct = {k: round(v / len(over30) * 100, 1) for k, v in reclassified.items()}

med_gap = tab["median_gap_days"].dropna()
result = {
    "global_measurement_end": str(GLOBAL_END.date()),
    "sync_lag_days": SYNC_LAG_DAYS,
    "cadence_factor": CADENCE_FACTOR,
    "equipment_total": int(tot),
    "share_last_seen_within_30d_of_end": round(last30_share, 4),
    "cause_counts": {k: int(v) for k, v in summary.items()},
    "cause_pct": summary_pct,
    "over30_subset_count": int(len(over30)),
    "over30_cause_counts": {k: int(v) for k, v in reclassified.items()},
    "over30_cause_pct": reclassified_pct,
    "median_inspection_gap_days": round(float(med_gap.median()), 1) if len(med_gap) else None,
    "p90_inspection_gap_days": round(float(med_gap.quantile(0.9)), 1) if len(med_gap) else None,
}

OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "censoring_diagnosis.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
tab.to_csv(OUTPUT / "equipment_censoring_profile.csv", index=False)

print(json.dumps(result, indent=2))
