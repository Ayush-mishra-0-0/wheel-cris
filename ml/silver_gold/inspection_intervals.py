"""Construct conservative consecutive inspection intervals from Business Truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

try:
    from .transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256, _write_parquet
    from .wheel_timeline import BUSINESS_TRUTH_VERSION
except ImportError:
    from transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256, _write_parquet
    from wheel_timeline import BUSINESS_TRUTH_VERSION


INTERVAL_CONTRACT_VERSION = "1.0.0"


def build_intervals(timeline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Create eligible same-locomotive consecutive intervals and audit exclusions."""
    required = ["measurement_record_id", "wheelset_equipment_id", "measurement_timestamp", "locomotive_id", "timeline_quality_tier"]
    missing = [column for column in required if column not in timeline]
    if missing:
        raise ValueError(f"Timeline missing required interval columns: {missing}")
    frame = timeline.loc[timeline["timeline_quality_tier"].eq("Gold B")].copy()
    frame = frame.sort_values(["wheelset_equipment_id", "measurement_timestamp", "measurement_record_id"])
    group = frame.groupby("wheelset_equipment_id", sort=False)
    frame["interval_end_measurement_id"] = group["measurement_record_id"].shift(-1)
    frame["interval_end_timestamp"] = group["measurement_timestamp"].shift(-1)
    frame["interval_end_locomotive_id"] = group["locomotive_id"].shift(-1)
    for column in ("wsmDia1", "wsmDia2", "wsmFlangeThickness1", "wsmFlangeThickness2", "wsmturning1", "wsmturning2"):
        if column in frame:
            frame[f"interval_end_{column}"] = group[column].shift(-1)
    candidates = frame.loc[frame["interval_end_measurement_id"].notna()].copy()
    candidates = candidates.rename(columns={"measurement_record_id": "interval_start_measurement_id", "measurement_timestamp": "interval_start_timestamp", "locomotive_id": "interval_start_locomotive_id"})
    candidates["interval_days"] = (candidates["interval_end_timestamp"] - candidates["interval_start_timestamp"]).dt.total_seconds() / 86400
    candidates["interval_quality_tier"] = "Gold C"
    candidates["interval_exclusion_reason"] = "non_positive_interval_days"
    candidates.loc[candidates["interval_days"].gt(0), "interval_exclusion_reason"] = "loco_changed_within_consecutive_inspections"
    same_loco = candidates["interval_start_locomotive_id"].eq(candidates["interval_end_locomotive_id"])
    eligible = candidates["interval_days"].gt(0) & same_loco
    candidates.loc[eligible, "interval_quality_tier"] = "Gold B"
    candidates.loc[eligible, "interval_exclusion_reason"] = pd.NA
    for field in ("wsmDia1", "wsmDia2", "wsmFlangeThickness1", "wsmFlangeThickness2"):
        end_field = f"interval_end_{field}"
        if field in candidates and end_field in candidates:
            candidates[f"delta_{field}"] = pd.to_numeric(candidates[end_field], errors="coerce") - pd.to_numeric(candidates[field], errors="coerce")
    candidates["interval_contract_version"] = INTERVAL_CONTRACT_VERSION
    candidates["business_truth_version"] = BUSINESS_TRUTH_VERSION
    intervals = candidates.loc[candidates["interval_quality_tier"].eq("Gold B")].copy()
    exclusions = candidates.loc[candidates["interval_quality_tier"].eq("Gold C")].copy()
    metrics = {"candidate_consecutive_pairs": len(candidates), "gold_b_intervals": len(intervals), "gold_c_interval_exclusions": len(exclusions), "exclusions_by_reason": exclusions["interval_exclusion_reason"].value_counts(dropna=False).to_dict()}
    return intervals, exclusions, metrics


def build_inspection_interval_pipeline() -> dict[str, Path]:
    timeline_path = GOLD_DIR / "business_truth" / BUSINESS_TRUTH_VERSION / "wheel_timeline_gold_b.parquet"
    intervals, exclusions, metrics = build_intervals(pd.read_parquet(timeline_path))
    run_id = str(uuid4())
    interval_dir = GOLD_DIR / "inspection_intervals" / "v1.0"
    interval_path = _write_parquet(intervals, interval_dir / "inspection_intervals_gold_b.parquet")
    exclusions_path = _write_parquet(exclusions, interval_dir / "inspection_intervals_gold_c_exclusions.parquet")
    report = {"run_id": run_id, "contract_version": INTERVAL_CONTRACT_VERSION, "business_truth_version": BUSINESS_TRUTH_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "timeline_sha256": _sha256(timeline_path), **metrics}
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUALITY_DIR / f"inspection_intervals_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return {"intervals": interval_path, "exclusions": exclusions_path, "quality_report": report_path}


if __name__ == "__main__":
    for name, path in build_inspection_interval_pipeline().items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
