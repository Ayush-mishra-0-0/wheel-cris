"""Point-in-time-safe Bronze-to-Silver wheel-measurement transformation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
QUALITY_DIR = PROJECT_ROOT / "reports" / "data_quality"
CONTRACT_VERSION = "1.0.0"
SENTINEL_DATES = {pd.Timestamp("1900-01-01"), pd.Timestamp("1899-12-30")}


def _append_flag(flags: pd.Series, mask: pd.Series, flag: str) -> pd.Series:
    """Append a semicolon-separated quality flag without overwriting evidence."""
    updated = flags.copy()
    previously_valid = updated.eq("valid")
    updated.loc[mask & previously_valid] = flag
    updated.loc[mask & ~previously_valid] += f";{flag}"
    return updated


def build_silver_measurements(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardise source-grain measurements and preserve all quality evidence.

    One input row remains one output row. We intentionally do not explode the
    two wheel-end measurements or infer a wheel identity until the equipment
    semantics and effective-dated assignment path are validated.
    """
    result = frame.copy()
    source_timestamp = result.get("wsmUpdatedOn", pd.Series(pd.NaT, index=result.index))
    measurement_timestamp = pd.to_datetime(source_timestamp, errors="coerce")
    invalid_timestamp = measurement_timestamp.isna() | measurement_timestamp.isin(SENTINEL_DATES)

    result["source_measurement_timestamp"] = source_timestamp
    result["measurement_timestamp"] = measurement_timestamp.mask(invalid_timestamp)
    result["measurement_date"] = result["measurement_timestamp"].dt.date
    result["quality_flags"] = "valid"
    result["quality_flags"] = _append_flag(result["quality_flags"], invalid_timestamp, "invalid_timestamp")

    if "wsmId" in result:
        result["measurement_record_id"] = pd.to_numeric(result["wsmId"], errors="coerce").astype("Int64")
        duplicate_id = result["measurement_record_id"].duplicated(keep=False) & result["measurement_record_id"].notna()
        result["quality_flags"] = _append_flag(result["quality_flags"], duplicate_id, "duplicate_measurement_id")

    if "wsmEquipmentId" in result:
        result["wheelset_equipment_id"] = pd.to_numeric(result["wsmEquipmentId"], errors="coerce").astype("Int64")
        missing_equipment = result["wheelset_equipment_id"].isna()
        result["quality_flags"] = _append_flag(result["quality_flags"], missing_equipment, "missing_equipment_id")

    # Keep observed source values and expose only plausibility flags. Limits are
    # not silently enforced here; engineering must approve them before scoring.
    plausibility_rules = {
        "wsmDia1": (500, 1300), "wsmDia2": (500, 1300),
        "wsmFlangeThickness1": (0, 80), "wsmFlangeThickness2": (0, 80),
        "wsmWheelGauge1": (1300, 1800), "wsmWheelGauge2": (1300, 1800),
    }
    for column, (lower, upper) in plausibility_rules.items():
        if column not in result:
            continue
        values = pd.to_numeric(result[column], errors="coerce")
        implausible = values.notna() & ~values.between(lower, upper)
        result["quality_flags"] = _append_flag(result["quality_flags"], implausible, f"implausible_{column}")

    result["record_status"] = "accepted"
    result.loc[result["quality_flags"].str.contains("invalid_timestamp|duplicate_measurement_id", regex=True), "record_status"] = "quarantined"
    result.loc[
        result["record_status"].eq("accepted") & result["quality_flags"].ne("valid"),
        "record_status",
    ] = "accepted_with_flags"
    result["contract_version"] = CONTRACT_VERSION
    return result


def build_silver_rtis_mileage(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardise source-grain RTIS mileage events without aggregating them."""
    result = frame.copy()
    event_time = pd.to_datetime(result.get("RlkdReportDate", pd.Series(pd.NaT, index=result.index)), errors="coerce")
    distance = pd.to_numeric(result.get("RlkdTotalDistance", pd.Series(pd.NA, index=result.index)), errors="coerce")
    result["rtis_mileage_event_id"] = pd.to_numeric(result.get("RlkdId", pd.Series(pd.NA, index=result.index)), errors="coerce").astype("Int64")
    result["loco_number"] = result.get("RlkdLocoNumber", pd.Series(pd.NA, index=result.index)).astype("string").str.strip()
    result["event_timestamp"] = event_time
    result["reported_distance_km"] = distance
    result["quality_flags"] = "valid"
    result["quality_flags"] = _append_flag(result["quality_flags"], event_time.isna() | event_time.isin(SENTINEL_DATES), "invalid_event_timestamp")
    result["quality_flags"] = _append_flag(result["quality_flags"], result["loco_number"].isna() | result["loco_number"].eq(""), "missing_loco_number")
    result["quality_flags"] = _append_flag(result["quality_flags"], distance.isna() | distance.lt(0), "invalid_reported_distance")
    duplicate_id = result["rtis_mileage_event_id"].duplicated(keep=False) & result["rtis_mileage_event_id"].notna()
    result["quality_flags"] = _append_flag(result["quality_flags"], duplicate_id, "duplicate_rtis_event_id")
    if "RlkdDivision" in result:
        business_key = pd.DataFrame({
            "loco": result["loco_number"],
            "date": result["event_timestamp"].dt.normalize(),
            "division": result["RlkdDivision"].astype("string").str.strip(),
            "distance": result["reported_distance_km"],
        })
        duplicate_business_report = business_key.duplicated(keep=False) & business_key.notna().all(axis=1)
        result["quality_flags"] = _append_flag(result["quality_flags"], duplicate_business_report, "duplicate_rtis_business_report")
    result["record_status"] = "accepted"
    result.loc[result["quality_flags"].str.contains("invalid_event_timestamp|duplicate_rtis_event_id", regex=True), "record_status"] = "quarantined"
    result.loc[result["record_status"].eq("accepted") & result["quality_flags"].ne("valid"), "record_status"] = "accepted_with_flags"
    result["contract_version"] = CONTRACT_VERSION
    return result


def build_silver_loco_equipment_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardise temporal equipment-to-locomotive assignment intervals."""
    result = frame.copy()
    provision = pd.to_datetime(result.get("LoehProvisionDate", pd.Series(pd.NaT, index=result.index)), errors="coerce")
    removed = pd.to_datetime(result.get("LoehRemovedDate", pd.Series(pd.NaT, index=result.index)), errors="coerce")
    result["assignment_history_id"] = pd.to_numeric(result.get("LoehId", pd.Series(pd.NA, index=result.index)), errors="coerce").astype("Int64")
    result["locomotive_id"] = pd.to_numeric(result.get("LoehLocoMaster", pd.Series(pd.NA, index=result.index)), errors="coerce").astype("Int64")
    result["equipment_id"] = pd.to_numeric(result.get("LoehEquipmentMasterRegister", pd.Series(pd.NA, index=result.index)), errors="coerce").astype("Int64")
    result["assignment_start_timestamp"] = provision.mask(provision.isin(SENTINEL_DATES))
    result["assignment_end_timestamp"] = removed.mask(removed.isin(SENTINEL_DATES))
    result["quality_flags"] = "valid"
    result["quality_flags"] = _append_flag(result["quality_flags"], result["assignment_history_id"].isna(), "missing_assignment_history_id")
    result["quality_flags"] = _append_flag(result["quality_flags"], result["equipment_id"].isna() | result["locomotive_id"].isna(), "missing_assignment_identity")
    result["quality_flags"] = _append_flag(result["quality_flags"], result["assignment_start_timestamp"].isna(), "invalid_provision_date")
    invalid_order = result["assignment_end_timestamp"].notna() & result["assignment_start_timestamp"].notna() & (result["assignment_end_timestamp"] < result["assignment_start_timestamp"])
    result["quality_flags"] = _append_flag(result["quality_flags"], invalid_order, "removed_before_provision")
    duplicate_id = result["assignment_history_id"].duplicated(keep=False) & result["assignment_history_id"].notna()
    result["quality_flags"] = _append_flag(result["quality_flags"], duplicate_id, "duplicate_assignment_history_id")
    result["record_status"] = "accepted"
    result.loc[result["quality_flags"].str.contains("missing_assignment_history_id|missing_assignment_identity|invalid_provision_date|removed_before_provision|duplicate_assignment_history_id", regex=True), "record_status"] = "quarantined"
    result["contract_version"] = CONTRACT_VERSION
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def build_pipeline() -> dict[str, Path]:
    """Build Silver, quarantine, quality evidence and a deliberately thin Gold view."""
    bronze_path = BRONZE_DIR / "wheel_measurements.parquet"
    source = pd.read_parquet(bronze_path)
    silver = build_silver_measurements(source)
    accepted = silver.loc[~silver["record_status"].eq("quarantined")].copy()
    quarantined = silver.loc[silver["record_status"].eq("quarantined")].copy()

    run_id = str(uuid4())
    silver_path = _write_parquet(accepted, SILVER_DIR / "wheel_measurements.parquet")
    quarantine_path = _write_parquet(quarantined, SILVER_DIR / "quarantine" / "wheel_measurements.parquet")

    # Gold is intentionally a source-grain hand-off until wheel identity and
    # engineering limits are validated. No future information is introduced.
    gold_columns = [column for column in (
        "measurement_record_id", "wheelset_equipment_id", "measurement_timestamp",
        "measurement_date", "record_status", "quality_flags", "contract_version",
    ) if column in accepted]
    gold_path = _write_parquet(accepted[gold_columns], GOLD_DIR / "wheel_measurement_snapshot_candidates.parquet")

    quality = {
        "run_id": run_id,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(bronze_path.relative_to(PROJECT_ROOT)), "sha256": _sha256(bronze_path), "rows": len(source)},
        "output": {"accepted_rows": len(accepted), "quarantined_rows": len(quarantined)},
        "quality_flag_counts": silver["quality_flags"].value_counts(dropna=False).to_dict(),
    }
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    quality_path = QUALITY_DIR / f"wheel_measurements_{run_id}.json"
    quality_path.write_text(json.dumps(quality, indent=2, default=str) + "\n", encoding="utf-8")
    return {"silver": silver_path, "quarantine": quarantine_path, "gold_candidates": gold_path, "quality_report": quality_path}


def build_rtis_mileage_pipeline() -> dict[str, Path]:
    """Build Silver RTIS events and a separate contract-quality report."""
    bronze_path = BRONZE_DIR / "rtis_mileage.parquet"
    source = pd.read_parquet(bronze_path)
    silver = build_silver_rtis_mileage(source)
    accepted = silver.loc[~silver["record_status"].eq("quarantined")].copy()
    quarantined = silver.loc[silver["record_status"].eq("quarantined")].copy()
    run_id = str(uuid4())
    silver_path = _write_parquet(accepted, SILVER_DIR / "rtis_mileage.parquet")
    quarantine_path = _write_parquet(quarantined, SILVER_DIR / "quarantine" / "rtis_mileage.parquet")
    quality = {
        "run_id": run_id,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(bronze_path.relative_to(PROJECT_ROOT)), "sha256": _sha256(bronze_path), "rows": len(source)},
        "output": {"accepted_rows": len(accepted), "quarantined_rows": len(quarantined)},
        "quality_flag_counts": silver["quality_flags"].value_counts(dropna=False).to_dict(),
    }
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    quality_path = QUALITY_DIR / f"rtis_mileage_{run_id}.json"
    quality_path.write_text(json.dumps(quality, indent=2, default=str) + "\n", encoding="utf-8")
    return {"silver": silver_path, "quarantine": quarantine_path, "quality_report": quality_path}


def build_loco_equipment_history_pipeline() -> dict[str, Path]:
    """Build the Silver temporal assignment ledger and quality evidence."""
    bronze_path = BRONZE_DIR / "loco_equipment_history.parquet"
    source = pd.read_parquet(bronze_path)
    silver = build_silver_loco_equipment_history(source)
    accepted = silver.loc[~silver["record_status"].eq("quarantined")].copy()
    quarantined = silver.loc[silver["record_status"].eq("quarantined")].copy()
    run_id = str(uuid4())
    silver_path = _write_parquet(accepted, SILVER_DIR / "loco_equipment_history.parquet")
    quarantine_path = _write_parquet(quarantined, SILVER_DIR / "quarantine" / "loco_equipment_history.parquet")
    quality = {"run_id": run_id, "contract_version": CONTRACT_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source": {"path": str(bronze_path.relative_to(PROJECT_ROOT)), "sha256": _sha256(bronze_path), "rows": len(source)}, "output": {"accepted_rows": len(accepted), "quarantined_rows": len(quarantined)}, "quality_flag_counts": silver["quality_flags"].value_counts(dropna=False).to_dict()}
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    quality_path = QUALITY_DIR / f"loco_equipment_history_{run_id}.json"
    quality_path.write_text(json.dumps(quality, indent=2, default=str) + "\n", encoding="utf-8")
    return {"silver": silver_path, "quarantine": quarantine_path, "quality_report": quality_path}


if __name__ == "__main__":
    for name, output in build_pipeline().items():
        print(f"{name}: {output.relative_to(PROJECT_ROOT)}")
    for name, output in build_rtis_mileage_pipeline().items():
        print(f"rtis_{name}: {output.relative_to(PROJECT_ROOT)}")
    for name, output in build_loco_equipment_history_pipeline().items():
        print(f"assignment_{name}: {output.relative_to(PROJECT_ROOT)}")
