"""Validate job-card maintenance timestamps against frozen inspection intervals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

try:
    from .transform import BRONZE_DIR, GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256
except ImportError:
    from transform import BRONZE_DIR, GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256


def validate_maintenance_inside_intervals(intervals: pd.DataFrame, jobcards: pd.DataFrame) -> dict:
    """Count job cards in (interval_start, interval_end] by assigned locomotive.

    `SejCreatedOn` is treated as the available maintenance-event timestamp;
    this validates temporal availability, not completion/effectiveness.
    """
    events = jobcards[["SejLocoId", "SejCreatedOn"]].copy()
    events["SejLocoId"] = pd.to_numeric(events["SejLocoId"], errors="coerce").astype("Int64")
    events["SejCreatedOn"] = pd.to_datetime(events["SejCreatedOn"], errors="coerce")
    events = events.dropna()
    counts = np.zeros(len(intervals), dtype=np.int64)
    indexed = intervals.reset_index(drop=False).rename(columns={"index": "interval_row"})
    for loco_id, interval_group in indexed.groupby("interval_start_locomotive_id", sort=False):
        event_times = events.loc[events["SejLocoId"].eq(loco_id), "SejCreatedOn"].sort_values().to_numpy()
        if len(event_times) == 0:
            continue
        starts = interval_group["interval_start_timestamp"].to_numpy()
        ends = interval_group["interval_end_timestamp"].to_numpy()
        counts[interval_group["interval_row"].to_numpy()] = np.searchsorted(event_times, ends, side="right") - np.searchsorted(event_times, starts, side="right")
    return {"jobcards_with_valid_loco_and_timestamp": len(events), "intervals_evaluated": len(intervals), "intervals_with_maintenance_event": int((counts > 0).sum()), "intervals_with_multiple_maintenance_events": int((counts > 1).sum()), "max_maintenance_events_in_interval": int(counts.max(initial=0))}


def run_maintenance_interval_validation() -> Path:
    interval_path = GOLD_DIR / "inspection_intervals" / "v1.0" / "inspection_intervals_gold_b.parquet"
    jobcard_path = BRONZE_DIR / "section_jobcards.parquet"
    metrics = validate_maintenance_inside_intervals(pd.read_parquet(interval_path), pd.read_parquet(jobcard_path, columns=["SejLocoId", "SejCreatedOn"]))
    report = {"run_id": str(uuid4()), "generated_at_utc": datetime.now(timezone.utc).isoformat(), "interval_sha256": _sha256(interval_path), "jobcard_sha256": _sha256(jobcard_path), "interval_boundary": "start < SejCreatedOn <= end", "metrics": metrics, "limitation": "Job-card creation time is not confirmed maintenance completion time; this is a temporal-presence validation only."}
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    output = QUALITY_DIR / f"maintenance_interval_validation_{report['run_id']}.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(run_maintenance_interval_validation().relative_to(PROJECT_ROOT))
