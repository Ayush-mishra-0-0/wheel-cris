"""Build the validated, point-in-time equipment/wheelset timeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

try:
    from .transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, SILVER_DIR, _sha256, _write_parquet
except ImportError:  # Script execution from the silver_gold directory.
    from transform import GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, SILVER_DIR, _sha256, _write_parquet

TIMELINE_CONTRACT_VERSION = "1.0.0"
BUSINESS_TRUTH_VERSION = "v1.0"


def classify_timeline(measurements: pd.DataFrame, history: pd.DataFrame, locomotives: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return Gold-B timeline rows, Gold-C exclusions, and validation metrics."""
    measurement_columns = [column for column in ("measurement_record_id", "wheelset_equipment_id", "measurement_timestamp", "measurement_date", "quality_flags", "record_status", "contract_version", "wsmDia1", "wsmDia2", "wsmFlangeThickness1", "wsmFlangeThickness2", "wsmturning1", "wsmturning2") if column in measurements]
    m = measurements.loc[measurements["record_status"].isin(["accepted", "accepted_with_flags"]), measurement_columns].copy()
    m = m.dropna(subset=["measurement_record_id", "wheelset_equipment_id", "measurement_timestamp"])
    h = history.loc[history["record_status"].eq("accepted"), ["assignment_history_id", "equipment_id", "locomotive_id", "assignment_start_timestamp", "assignment_end_timestamp"]].copy()
    h = h.dropna(subset=["assignment_history_id", "equipment_id", "locomotive_id", "assignment_start_timestamp"])
    has_history = set(h["equipment_id"].dropna().astype("int64"))
    outside_cohort_history_count = int((~m["wheelset_equipment_id"].astype("int64").isin(has_history)).sum())
    # The history input is cohort-filtered (WAP7). Restrict Gold-B/Gold-C to
    # that candidate universe; do not label the rest of the full-fleet Bronze
    # measurement table as a WAP7 timeline failure.
    m = m.loc[m["wheelset_equipment_id"].astype("int64").isin(has_history)].copy()
    merged = m.merge(h, how="left", left_on="wheelset_equipment_id", right_on="equipment_id", sort=False)
    interval_match = merged["assignment_history_id"].notna() & (merged["measurement_timestamp"] >= merged["assignment_start_timestamp"]) & (merged["assignment_end_timestamp"].isna() | (merged["measurement_timestamp"] <= merged["assignment_end_timestamp"]))
    matched = merged.loc[interval_match].copy()
    match_counts = matched.groupby("measurement_record_id").size().rename("assignment_interval_count")
    m = m.merge(match_counts, how="left", on="measurement_record_id")
    m["assignment_interval_count"] = m["assignment_interval_count"].fillna(0).astype("int64")
    m["timeline_quality_tier"] = "Gold C"
    m["timeline_exclusion_reason"] = "no_valid_assignment_interval"
    m.loc[m["assignment_interval_count"].eq(1), "timeline_quality_tier"] = "Gold B"
    m.loc[m["assignment_interval_count"].eq(1), "timeline_exclusion_reason"] = pd.NA
    m.loc[m["assignment_interval_count"].gt(1), "timeline_exclusion_reason"] = "ambiguous_assignment_interval"
    eligible_ids = set(m.loc[m["timeline_quality_tier"].eq("Gold B"), "measurement_record_id"])
    timeline = matched.loc[matched["measurement_record_id"].isin(eligible_ids)].copy()
    timeline = timeline.merge(m[["measurement_record_id", "assignment_interval_count", "timeline_quality_tier", "timeline_exclusion_reason"]], how="inner", on="measurement_record_id")
    loco_columns = [column for column in ("LomId", "LomNumber", "LocoType", "LomStatus") if column in locomotives]
    timeline = timeline.merge(locomotives[loco_columns], how="left", left_on="locomotive_id", right_on="LomId")
    timeline["timeline_contract_version"] = TIMELINE_CONTRACT_VERSION
    timeline["asset_identity_level"] = "equipment_or_wheelset_pending_semantic_validation"
    exclusions = m.loc[m["timeline_quality_tier"].eq("Gold C")].copy()
    exclusions["timeline_contract_version"] = TIMELINE_CONTRACT_VERSION
    exclusions["asset_identity_level"] = "equipment_or_wheelset_pending_semantic_validation"
    metrics = {"measurements_outside_cohort_history_universe": outside_cohort_history_count, "measurements_evaluated": len(m), "gold_b_timeline_rows": len(timeline), "gold_c_exclusions": len(exclusions), "exclusions_by_reason": exclusions["timeline_exclusion_reason"].value_counts(dropna=False).to_dict()}
    return timeline, exclusions, metrics


def build_wheel_timeline_pipeline() -> dict[str, Path]:
    measurements_path = SILVER_DIR / "wheel_measurements.parquet"
    history_path = SILVER_DIR / "loco_equipment_history.parquet"
    cohort_path = PROJECT_ROOT / "data" / "bronze" / "cohort_locomotives.parquet"
    timeline, exclusions, metrics = classify_timeline(pd.read_parquet(measurements_path), pd.read_parquet(history_path), pd.read_parquet(cohort_path))
    run_id = str(uuid4())
    release_dir = GOLD_DIR / "business_truth" / BUSINESS_TRUTH_VERSION
    timeline_path = _write_parquet(timeline, release_dir / "wheel_timeline_gold_b.parquet")
    exclusions_path = _write_parquet(exclusions, release_dir / "wheel_timeline_gold_c_exclusions.parquet")
    report = {"run_id": run_id, "business_truth_version": BUSINESS_TRUTH_VERSION, "contract_version": TIMELINE_CONTRACT_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "inputs": {"silver_wheel_measurements_sha256": _sha256(measurements_path), "silver_loco_equipment_history_sha256": _sha256(history_path), "cohort_sha256": _sha256(cohort_path)}, **metrics}
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUALITY_DIR / f"wheel_timeline_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return {"timeline": timeline_path, "exclusions": exclusions_path, "quality_report": report_path}


if __name__ == "__main__":
    for name, path in build_wheel_timeline_pipeline().items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
