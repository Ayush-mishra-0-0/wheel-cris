"""Build semantics-aware Operational Exposure from frozen inspection intervals.

Distance is deliberately absent.  RTIS mileage is represented only as reporting
metadata until its source owner confirms the physical meaning of its values.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

try:
    from .transform import BRONZE_DIR, GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256, _write_parquet
except ImportError:
    from transform import BRONZE_DIR, GOLD_DIR, PROJECT_ROOT, QUALITY_DIR, _sha256, _write_parquet


OPERATIONAL_EXPOSURE_VERSION = "v1.0"
DISTANCE_STATUS = "BLOCKED_PENDING_SOURCE_CONFIRMATION"


def _normalise_loco_number(values: pd.Series) -> pd.Series:
    """Apply the already-validated numeric locomotive identifier normalization."""
    raw = values.astype("string").str.strip().str.upper().str.replace(r"\s+", "", regex=True)
    numeric = pd.to_numeric(raw, errors="coerce")
    return numeric.astype("Int64").astype("string").where(numeric.notna(), raw)


def _count_events(intervals: pd.DataFrame, events: pd.DataFrame, interval_loco: str, event_loco: str, event_time: str) -> np.ndarray:
    """Count events in the point-in-time-safe boundary (start, end]."""
    counts = np.zeros(len(intervals), dtype=np.int64)
    # Build the source index once.  Re-filtering a multi-million-row event
    # source for every locomotive is both slow and operationally unsafe.
    event_index = {loco: group[event_time].dropna().sort_values().to_numpy() for loco, group in events.groupby(event_loco, sort=False)}
    indexed = intervals.reset_index(drop=False).rename(columns={"index": "interval_row"})
    for loco, group in indexed.groupby(interval_loco, sort=False):
        times = event_index.get(loco)
        if times is None or len(times) == 0:
            continue
        rows = group["interval_row"].to_numpy()
        counts[rows] = np.searchsorted(times, group["interval_end_timestamp"].to_numpy(), side="right") - np.searchsorted(times, group["interval_start_timestamp"].to_numpy(), side="right")
    return counts


def _rtis_metadata(intervals: pd.DataFrame, rtis: pd.DataFrame) -> pd.DataFrame:
    """Return reporting metadata; never aggregates RlkdTotalDistance."""
    count = np.zeros(len(intervals), dtype=np.int64)
    division_count = np.zeros(len(intervals), dtype=np.int64)
    duplicate_count = np.zeros(len(intervals), dtype=np.int64)
    reporting_days = np.zeros(len(intervals), dtype=np.int64)
    earliest = np.full(len(intervals), np.datetime64("NaT"), dtype="datetime64[ns]")
    latest = np.full(len(intervals), np.datetime64("NaT"), dtype="datetime64[ns]")

    events = rtis.copy()
    events["loco_key"] = _normalise_loco_number(events["loco_number"])
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"], errors="coerce")
    events = events.dropna(subset=["loco_key", "event_timestamp"])
    # Duplicate business reports are explicitly counted, never silently removed.
    key = ["loco_key", "event_timestamp", "RlkdDivision"]
    events["is_duplicate_business_report"] = events.duplicated(key, keep="first")
    # RTIS already reports at a date grain.  Keep individual records so the
    # report and duplicate counts retain their original provenance, but index
    # them once by locomotive for interval lookup.
    rtis_index = {loco: group.sort_values("event_timestamp") for loco, group in events.groupby("loco_key", sort=False)}
    indexed = intervals.reset_index(drop=False).rename(columns={"index": "interval_row"})
    for loco, group in indexed.groupby("loco_number_key", sort=False):
        subset = rtis_index.get(loco)
        if subset is None or subset.empty:
            continue
        times = subset["event_timestamp"].to_numpy(dtype="datetime64[ns]")
        divisions = subset["RlkdDivision"].astype("string").fillna("<missing>").to_numpy()
        duplicates = subset["is_duplicate_business_report"].to_numpy(dtype=np.int64)
        duplicate_prefix = np.r_[0, np.cumsum(duplicates)]
        day_values = times.astype("datetime64[D]")
        unique_days = np.unique(day_values)
        rows = group["interval_row"].to_numpy()
        starts = group["interval_start_timestamp"].to_numpy(dtype="datetime64[ns]")
        ends = group["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
        left = np.searchsorted(times, starts, side="right")
        right = np.searchsorted(times, ends, side="right")
        count[rows] = right - left
        duplicate_count[rows] = duplicate_prefix[right] - duplicate_prefix[left]
        reporting_days[rows] = (np.searchsorted(unique_days, ends.astype("datetime64[D]"), side="right") - np.searchsorted(unique_days, starts.astype("datetime64[D]"), side="right"))
        present = right > left
        earliest[rows[present]] = times[left[present]]
        latest[rows[present]] = times[right[present] - 1]
        # Unique divisions are intentionally a reporting-context metric, not a
        # route reconstruction.  NumPy avoids costly DataFrame slicing here.
        for row, l, r in zip(rows[present], left[present], right[present]):
            division_count[row] = len(np.unique(divisions[l:r]))
    result = pd.DataFrame({"rtis_report_count": count, "rtis_division_count": division_count, "rtis_duplicate_report_count": duplicate_count, "rtis_earliest_report_timestamp": earliest, "rtis_latest_report_timestamp": latest, "rtis_reporting_days": reporting_days}, index=intervals.index)
    result["rtis_coverage_pct"] = np.where(intervals["interval_days"].gt(0), (result["rtis_reporting_days"] / intervals["interval_days"]) * 100, np.nan)
    return result


def _event_type_metadata(intervals: pd.DataFrame, events: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Produce auditable source-event type context for intervals with events."""
    type_count = np.zeros(len(intervals), dtype=np.int64)
    type_values = np.full(len(intervals), pd.NA, dtype=object)
    indexed = intervals.reset_index(drop=False).rename(columns={"index": "interval_row"})
    event_index = {loco: group.sort_values("event_timestamp") for loco, group in events.groupby("loco_number_key", sort=False)}
    for loco, group in indexed.groupby("loco_number_key", sort=False):
        subset = event_index.get(loco)
        if subset is None:
            continue
        times = subset["event_timestamp"].to_numpy(dtype="datetime64[ns]")
        event_types = subset["EVENT_TYPE"].astype("string").fillna("<missing>").to_numpy()
        starts = group["interval_start_timestamp"].to_numpy(dtype="datetime64[ns]")
        ends = group["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
        left = np.searchsorted(times, starts, side="right")
        right = np.searchsorted(times, ends, side="right")
        rows = group["interval_row"].to_numpy()
        present = right > left
        for row, l, r in zip(rows[present], left[present], right[present]):
            values = sorted(set(event_types[l:r].tolist()))
            type_count[row] = len(values)
            type_values[row] = json.dumps(values, separators=(",", ":"))
    return type_count, type_values


def build_operational_exposure(intervals: pd.DataFrame, emergency: pd.DataFrame, jobcards: pd.DataFrame, rtis: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach verified events and provisional RTIS reporting metadata to intervals."""
    required = {"interval_start_measurement_id", "interval_end_measurement_id", "interval_start_timestamp", "interval_end_timestamp", "interval_days", "interval_start_locomotive_id", "LomNumber"}
    missing = required - set(intervals.columns)
    if missing:
        raise ValueError(f"Intervals missing required operational-exposure columns: {sorted(missing)}")
    output = intervals[["interval_start_measurement_id", "interval_end_measurement_id", "wheelset_equipment_id", "interval_start_timestamp", "interval_end_timestamp", "interval_days", "interval_start_locomotive_id", "LomNumber"]].copy()
    output = output.rename(columns={"interval_start_locomotive_id": "locomotive_id", "LomNumber": "locomotive_number"})
    output["operational_exposure_id"] = "OE-" + output["interval_start_measurement_id"].astype("string") + "-" + output["interval_end_measurement_id"].astype("string")
    output["loco_number_key"] = _normalise_loco_number(output["locomotive_number"])

    emergency_events = emergency[["IrledId", "LOCO_NO", "EVENT_TYPE", "EVENT_TRANSMISSION_TIME"]].copy()
    emergency_events["loco_number_key"] = _normalise_loco_number(emergency_events["LOCO_NO"])
    emergency_events["event_timestamp"] = pd.to_datetime(emergency_events["EVENT_TRANSMISSION_TIME"], errors="coerce")
    emergency_events = emergency_events.dropna(subset=["loco_number_key", "event_timestamp"])
    output["emergency_event_count"] = _count_events(output, emergency_events, "loco_number_key", "loco_number_key", "event_timestamp")
    output["emergency_event_type_count"], output["emergency_event_types"] = _event_type_metadata(output, emergency_events)
    output["emergency_event_status"] = "READY_SOURCE_EVENT_COUNT_EVENT_CODE_SEMANTICS_PENDING"

    maintenance_events = jobcards[["SejId", "SejLocoId", "SejCreatedOn"]].copy()
    maintenance_events["locomotive_id"] = pd.to_numeric(maintenance_events["SejLocoId"], errors="coerce").astype("Int64")
    maintenance_events["event_timestamp"] = pd.to_datetime(maintenance_events["SejCreatedOn"], errors="coerce")
    maintenance_events = maintenance_events.dropna(subset=["locomotive_id", "event_timestamp"])
    output["maintenance_jobcard_count"] = _count_events(output, maintenance_events, "locomotive_id", "locomotive_id", "event_timestamp")
    output["maintenance_event_status"] = "READY_JOB_CARD_CREATION_EVENT_ONLY"

    output = pd.concat([output, _rtis_metadata(output, rtis)], axis=1)
    output["rtis_metadata_status"] = "PROVISIONAL_REPORTING_METADATA_ONLY"
    output["distance_status"] = DISTANCE_STATUS
    output["distance_km"] = np.nan
    output["feature_contract_version"] = OPERATIONAL_EXPOSURE_VERSION
    output["interval_boundary_rule"] = "start_exclusive_end_inclusive"
    output["quality_flags"] = np.where(output["rtis_report_count"].eq(0), "no_rtis_reports_in_interval", "valid")
    output = output.drop(columns=["loco_number_key"])
    metrics = {
        "intervals": len(output), "intervals_with_emergency_events": int(output["emergency_event_count"].gt(0).sum()),
        "intervals_with_jobcard_events": int(output["maintenance_jobcard_count"].gt(0).sum()), "intervals_with_rtis_reports": int(output["rtis_report_count"].gt(0).sum()),
        "intervals_without_rtis_reports": int(output["rtis_report_count"].eq(0).sum()), "distance_status": DISTANCE_STATUS,
    }
    return output, metrics


def build_operational_exposure_pipeline() -> dict[str, Path]:
    interval_path = GOLD_DIR / "inspection_intervals" / "v1.0" / "inspection_intervals_gold_b.parquet"
    emergency_path = BRONZE_DIR / "rtis_emergency.parquet"
    jobcard_path = BRONZE_DIR / "section_jobcards.parquet"
    rtis_path = PROJECT_ROOT / "data" / "silver" / "rtis_mileage.parquet"
    exposure, metrics = build_operational_exposure(pd.read_parquet(interval_path), pd.read_parquet(emergency_path), pd.read_parquet(jobcard_path, columns=["SejId", "SejLocoId", "SejCreatedOn"]), pd.read_parquet(rtis_path))
    output_path = _write_parquet(exposure, GOLD_DIR / "operational_exposure" / OPERATIONAL_EXPOSURE_VERSION / "inspection_interval_operational_exposure.parquet")
    run_id = str(uuid4())
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUALITY_DIR / f"operational_exposure_{run_id}.json"
    report_path.write_text(json.dumps({"run_id": run_id, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "version": OPERATIONAL_EXPOSURE_VERSION, "input_sha256": {"intervals": _sha256(interval_path), "emergency": _sha256(emergency_path), "jobcards": _sha256(jobcard_path), "rtis": _sha256(rtis_path)}, "semantic_limits": {"maintenance": "Job-card creation time only; not confirmed completion or effectiveness.", "rtis": "Reporting metadata only; no distance aggregation or interpretation.", "emergency": "Transmission timestamp event count."}, "metrics": metrics}, indent=2) + "\n", encoding="utf-8")
    return {"operational_exposure": output_path, "quality_report": report_path}


if __name__ == "__main__":
    for name, path in build_operational_exposure_pipeline().items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
