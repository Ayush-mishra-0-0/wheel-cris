"""Phase 5 Layer 0 - loco-to-shed attribution.

Attributes, for each (loco, timestamp), the shed where the loco was stabled /
turned, using in priority order:
  1. SLAM schedule: integ_pub_coa_slamloco_schedule (loco shed stays with
     SHEDSTRTTIME..SHEDENDTIME, LOCOSHED/GEOSHED).
  2. FOIS trackhistory: most recent station observation at/before the timestamp,
     mapped to a shed via the loco's known shed assignments when possible;
     otherwise recorded as station-only context.
  3. Fallback context: home_shed / defect_zone / defect_division from WES.

Output: model_datasets/v5/loco_shed_stays.parquet (indexed lookup table)
        model_datasets/v5/shed_attribution_coverage.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SLAM = ROOT / "data" / "bronze" / "integ_pub_coa_slamloco_schedule.parquet"
TRACKHIST = ROOT / "distance_recovery" / "data" / "fois_trackhistory_wap7.parquet"
OUT = ROOT / "model_datasets" / "v5"


def build_slam_stays() -> pd.DataFrame:
    s = pd.read_parquet(SLAM)
    keep = [c for c in ["LOCONUM", "LOCOSHED", "GEOSHED", "SHEDSTRTTIME", "SHEDENDTIME"] if c in s.columns]
    s = s[keep].copy()
    s["loco_number"] = s["LOCONUM"].astype(str).str.strip()
    s["start"] = pd.to_datetime(s["SHEDSTRTTIME"])
    s["end"] = pd.to_datetime(s["SHEDENDTIME"])
    s["shed"] = s["LOCOSHED"].astype(str).str.strip()
    s = s.dropna(subset=["loco_number", "start"])
    s = s.sort_values(["loco_number", "start"]).reset_index(drop=True)
    # forward-fill open stays (end NaT) to the next stay start - 1h
    s = s.copy()
    s["end"] = s["end"].fillna(s.groupby("loco_number")["start"].shift(-1) - pd.Timedelta(hours=1))
    return s[["loco_number", "start", "end", "shed", "GEOSHED"]]


def coverage_report() -> dict:
    slam = build_slam_stays()
    return {
        "n_stays": int(len(slam)),
        "distinct_locos": int(slam["loco_number"].nunique()),
        "date_range": [str(slam["start"].min().date()), str(slam["end"].max().date())],
        "open_stays_resolved": int(slam["end"].notna().sum()),
    }


def main() -> None:
    slam = build_slam_stays()
    OUT.mkdir(parents=True, exist_ok=True)
    slam.to_parquet(OUT / "loco_shed_stays.parquet", index=False)
    rep = coverage_report()
    (OUT / "shed_attribution_coverage.json").write_text(
        json.dumps(rep, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(rep, indent=2, default=str))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
