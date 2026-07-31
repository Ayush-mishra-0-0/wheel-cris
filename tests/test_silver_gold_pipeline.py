import pandas as pd

from silver_gold.transform import build_silver_measurements, build_silver_rtis_mileage, build_silver_loco_equipment_history
from silver_gold.wheel_timeline import classify_timeline
from silver_gold.inspection_intervals import build_intervals
from silver_gold.operational_exposure import DISTANCE_STATUS, build_operational_exposure
from silver_gold.validate_feature_specification import load_and_validate
from feature_store.feature_store_builder import build_feature_store


def test_build_silver_measurements_adds_quality_flags_and_dates() -> None:
    frame = pd.DataFrame(
        {
            "wsmEquipmentId": [101, 102],
            "wsmUpdatedOn": [pd.Timestamp("2024-01-01"), pd.NaT],
            "wsmDia1": [1080.0, 1090.0],
            "wsmFlange1": [1.2, 1.3],
        }
    )

    result = build_silver_measurements(frame)

    assert "measurement_date" in result.columns
    assert result.loc[0, "measurement_date"] == pd.Timestamp("2024-01-01").date()
    assert result.loc[1, "quality_flags"] == "invalid_timestamp"
    assert result.loc[0, "quality_flags"] == "valid"


def test_build_silver_rtis_mileage_flags_invalid_distance() -> None:
    frame = pd.DataFrame(
        {
            "RlkdId": [1, 2],
            "RlkdLocoNumber": ["37100", "37101"],
            "RlkdReportDate": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
            "RlkdTotalDistance": [15.0, -1.0],
        }
    )

    result = build_silver_rtis_mileage(frame)

    assert result.loc[0, "reported_distance_km"] == 15.0
    assert result.loc[1, "quality_flags"] == "invalid_reported_distance"
    assert result.loc[1, "record_status"] == "accepted_with_flags"


def test_loco_equipment_history_quarantines_invalid_interval() -> None:
    frame = pd.DataFrame({"LoehId": [1], "LoehLocoMaster": [10], "LoehEquipmentMasterRegister": [100], "LoehProvisionDate": [pd.Timestamp("2024-02-01")], "LoehRemovedDate": [pd.Timestamp("2024-01-01")]})
    result = build_silver_loco_equipment_history(frame)
    assert result.loc[0, "record_status"] == "quarantined"
    assert "removed_before_provision" in result.loc[0, "quality_flags"]


def test_timeline_keeps_only_exactly_one_assignment_interval() -> None:
    measurements = pd.DataFrame({"measurement_record_id": [1, 2], "wheelset_equipment_id": [100, 200], "measurement_timestamp": [pd.Timestamp("2024-01-10"), pd.Timestamp("2024-01-10")], "record_status": ["accepted", "accepted"], "quality_flags": ["valid", "valid"]})
    history = pd.DataFrame({"assignment_history_id": [10, 20, 21], "equipment_id": [100, 200, 200], "locomotive_id": [1, 2, 3], "assignment_start_timestamp": [pd.Timestamp("2024-01-01")] * 3, "assignment_end_timestamp": [pd.NaT, pd.NaT, pd.NaT], "record_status": ["accepted"] * 3})
    locomotives = pd.DataFrame({"LomId": [1, 2, 3], "LomNumber": ["1", "2", "3"], "LocoType": ["WAP7"] * 3})
    timeline, exclusions, _ = classify_timeline(measurements, history, locomotives)
    assert timeline["measurement_record_id"].tolist() == [1]
    assert exclusions.loc[exclusions["measurement_record_id"].eq(2), "timeline_exclusion_reason"].iloc[0] == "ambiguous_assignment_interval"


def test_intervals_exclude_locomotive_change() -> None:
    timeline = pd.DataFrame({"measurement_record_id": [1, 2, 3], "wheelset_equipment_id": [100, 100, 200], "measurement_timestamp": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-11"), pd.Timestamp("2024-01-01")], "locomotive_id": [10, 10, 20], "timeline_quality_tier": ["Gold B"] * 3})
    intervals, exclusions, _ = build_intervals(timeline)
    assert len(intervals) == 1
    assert intervals.iloc[0]["interval_days"] == 10
    assert len(exclusions) == 0


def test_operational_exposure_keeps_distance_blocked_and_counts_events() -> None:
    intervals = pd.DataFrame({"interval_start_measurement_id": [1], "interval_end_measurement_id": [2], "wheelset_equipment_id": [100], "interval_start_timestamp": [pd.Timestamp("2024-01-01")], "interval_end_timestamp": [pd.Timestamp("2024-01-11")], "interval_days": [10.0], "interval_start_locomotive_id": [10], "LomNumber": ["00123"]})
    emergency = pd.DataFrame({"IrledId": [1], "LOCO_NO": ["123"], "EVENT_TYPE": ["EB"], "EVENT_TRANSMISSION_TIME": [pd.Timestamp("2024-01-05")]})
    jobcards = pd.DataFrame({"SejId": [1], "SejLocoId": [10], "SejCreatedOn": [pd.Timestamp("2024-01-08")]})
    rtis = pd.DataFrame({"loco_number": ["123"], "event_timestamp": [pd.Timestamp("2024-01-04")], "RlkdDivision": ["DLI"]})
    exposure, _ = build_operational_exposure(intervals, emergency, jobcards, rtis)
    assert exposure.loc[0, "emergency_event_count"] == 1
    assert exposure.loc[0, "maintenance_jobcard_count"] == 1
    assert exposure.loc[0, "rtis_report_count"] == 1
    assert exposure.loc[0, "distance_status"] == DISTANCE_STATUS
    assert pd.isna(exposure.loc[0, "distance_km"])


def test_engineering_feature_specification_is_valid() -> None:
    specification = load_and_validate()
    assert specification["specification_version"] == "1.0.0"
    assert any(feature["feature_id"] == "interval_distance_km" and feature["status"] == "BLOCKED" for feature in specification["features"])


def test_feature_store_admits_only_approved_features() -> None:
    outputs = build_feature_store()
    registry = __import__("json").loads(outputs["feature_registry"].read_text(encoding="utf-8"))
    materialised_ids = {item["feature_id"] for item in registry["materialised_features"]}
    excluded_ids = {item["feature_id"] for item in registry["excluded_features"]}
    assert "interval_distance_km" not in materialised_ids
    assert "interval_distance_km" in excluded_ids
    assert all(item["status"] in {"READY", "READY_WITH_CAVEAT", "READY_FOR_MATERIALISATION"} for item in registry["materialised_features"])
