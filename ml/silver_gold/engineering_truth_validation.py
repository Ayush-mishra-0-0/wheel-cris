"""Engineering sanity checks for the frozen timeline and interval contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

try:
    from .transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256
except ImportError:
    from transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256


def validate_intervals(intervals: pd.DataFrame) -> dict:
    """Report raw engineering sanity evidence; do not alter source intervals."""
    checks = {
        "interval_rows": len(intervals),
        "non_positive_days": int((intervals["interval_days"] <= 0).sum()),
        "loco_endpoint_mismatch": int((intervals["interval_start_locomotive_id"] != intervals["interval_end_locomotive_id"]).sum()),
        "duplicate_interval_endpoint_pairs": int(intervals.duplicated(["interval_start_measurement_id", "interval_end_measurement_id"]).sum()),
    }
    for field in ("wsmDia1", "wsmDia2", "wsmFlangeThickness1", "wsmFlangeThickness2"):
        delta_field = f"delta_{field}"
        if delta_field in intervals:
            delta = pd.to_numeric(intervals[delta_field], errors="coerce")
            checks[f"{delta_field}_non_null"] = int(delta.notna().sum())
            checks[f"{delta_field}_positive_count"] = int((delta > 0).sum())
            checks[f"{delta_field}_negative_count"] = int((delta < 0).sum())
    return checks


def run_engineering_truth_validation() -> Path:
    interval_path = GOLD_DIR / "inspection_intervals" / "v1.0" / "inspection_intervals_gold_b.parquet"
    checks = validate_intervals(pd.read_parquet(interval_path))
    report = {
        "run_id": str(uuid4()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interval_contract_version": "1.0.0",
        "input_sha256": _sha256(interval_path),
        "checks": checks,
        "interpretation": "Positive/negative geometry deltas are raw observations, not yet accepted wear labels. Their meaning requires approved measurement and turning/reprofiling business rules.",
    }
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUALITY_DIR / f"engineering_truth_validation_{report['run_id']}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path


if __name__ == "__main__":
    print(run_engineering_truth_validation().relative_to(PROJECT_ROOT))
