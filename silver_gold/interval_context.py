"""Build interval-context enrichment: wheel/axle position, inspection count,
wheel profile, schedule, home shed, zone/division, and wheel-age proxy at the
inspection-interval grain.

Point-in-time rule: every value is the state *at* interval_end_timestamp using
only source facts with business time at or before the interval end.
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


INTERVAL_CONTEXT_VERSION = "v1.0"


def _latest_at_or_before(values: pd.DataFrame, keys: list[str], time_col: str, end: pd.DataFrame, out: str) -> pd.Series:
    """For each key group, take the source value whose time is the latest <= interval end."""
    result = pd.Series(pd.NA, index=end.index, dtype=object)
    if values.empty or values.dropna(subset=[time_col] + keys).empty:
        return result
    frame = values.copy()
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce")
    frame = frame.dropna(subset=[time_col] + keys)
    for k in keys:
        if frame[k].dtype == object or isinstance(frame[k].dtype, pd.StringDtype):
            frame[k] = frame[k].astype("string").fillna("")
            end[k] = end[k].astype("string").fillna("")
    frame[time_col] = frame[time_col].astype("datetime64[ns]")
    ends = pd.to_datetime(end["interval_end_timestamp"], errors="coerce").astype("datetime64[ns]").to_numpy()

    indexed = end.reset_index(drop=False).rename(columns={"index": "row"})
    source = frame.sort_values(keys + [time_col])
    source_times = source[time_col].to_numpy()
    source_vals = source[out].to_numpy()
    for key_vals, group in indexed.groupby(keys, sort=False):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        subset_mask = np.ones(len(source), dtype=bool)
        for k, v in zip(keys, key_vals):
            subset_mask &= (source[k].to_numpy() == v)
        if not subset_mask.any():
            continue
        idx = np.flatnonzero(subset_mask)
        sel_times = source_times[idx]
        sel_vals = source_vals[idx]
        pos = np.searchsorted(sel_times, ends[group["row"].to_numpy()], side="right") - 1
        rows = group["row"].to_numpy()
        hit = pos >= 0
        if hit.any():
            result.iloc[rows[hit]] = sel_vals[pos[hit]]
    return result


def build_interval_context(
    intervals: pd.DataFrame,
    wheel_measurements: pd.DataFrame,
    formation: pd.DataFrame,
    wheel_register: pd.DataFrame,
    daily_overdue: pd.DataFrame,
    defects: pd.DataFrame,
    equipment_master: pd.DataFrame,
) -> pd.DataFrame:
    """Attach source-derived context features to each inspection interval."""
    required = {"interval_start_measurement_id", "interval_end_measurement_id", "interval_end_timestamp", "wheelset_equipment_id", "LomNumber", "interval_start_locomotive_id"}
    missing = required - set(intervals.columns)
    if missing:
        raise ValueError(f"Intervals missing required interval-context columns: {sorted(missing)}")

    out = intervals[["interval_start_measurement_id", "interval_end_measurement_id", "interval_end_timestamp", "wheelset_equipment_id", "LomNumber", "interval_start_locomotive_id"]].copy()

    # --- Wheel/axle position, register reference and inspection count ---
    wm = wheel_measurements[["wsmId", "wsmEquipmentId", "wsmWRId", "wsmWheelSetPosition", "wsmW1EndType", "wsmUpdatedOn", "wsmturning1", "wsmProvDate"]].copy()
    wm["wsmId"] = pd.to_numeric(wm["wsmId"], errors="coerce").astype("Int64")
    wm["wsmEquipmentId"] = pd.to_numeric(wm["wsmEquipmentId"], errors="coerce").astype("Int64")
    wm["wsmWRId"] = pd.to_numeric(wm["wsmWRId"], errors="coerce").astype("Int64")
    wm["wsmWheelSetPosition"] = pd.to_numeric(wm["wsmWheelSetPosition"], errors="coerce").astype("Int64")
    wm["wsmW1EndType"] = pd.to_numeric(wm["wsmW1EndType"], errors="coerce").astype("Int64")
    wm["wsmturning1"] = pd.to_numeric(wm["wsmturning1"], errors="coerce").astype("Int64")
    wm["wsmProvDate"] = pd.to_datetime(wm["wsmProvDate"], errors="coerce")
    wm["wsmUpdatedOn"] = pd.to_datetime(wm["wsmUpdatedOn"], errors="coerce")

    endpoint = out["interval_end_measurement_id"].rename("wsmId").to_frame()
    endpoint["wsmId"] = pd.to_numeric(endpoint["wsmId"], errors="coerce").astype("Int64")
    joined = endpoint.merge(wm, on="wsmId", how="left", validate="one_to_one")
    out["axle_position_1_6"] = joined["wsmWheelSetPosition"]
    out["wheel_wr_id"] = joined["wsmWRId"]
    out["turning_indicator_raw"] = joined["wsmturning1"]

    formation["pos_key"] = formation["WftWSPos"].astype(str) + "_" + formation["WftEndType"].astype(int).astype(str)
    joined["pos_key"] = joined["wsmWheelSetPosition"].astype("string") + "_" + joined["wsmW1EndType"].astype("string")
    out["wheel_position_1_12"] = joined.merge(formation[["pos_key", "WftWheelPos"]], on="pos_key", how="left")["WftWheelPos"]

    # Inspection count per wheelset equipment (stable identity) up to and including interval end.
    counts = np.zeros(len(out), dtype=np.int64)
    wm_clean = wm.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).sort_values("wsmUpdatedOn")
    indexed = out.reset_index(drop=False).rename(columns={"index": "row"})
    equipment_index = {eid: group["wsmUpdatedOn"].to_numpy(dtype="datetime64[ns]") for eid, group in wm_clean.groupby("wsmEquipmentId", sort=False)}
    indexed["equipment_key"] = joined["wsmEquipmentId"].to_numpy()
    for eid, group in indexed.groupby("equipment_key", sort=False):
        times = equipment_index.get(eid)
        if times is None or len(times) == 0:
            continue
        rows = group["row"].to_numpy()
        ends = group["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
        counts[rows] = np.searchsorted(times, ends, side="right")
    out["inspection_count_through_interval_end"] = counts

    # Days since last turning per wheelset equipment (stable identity), at interval end.
    days_since = np.full(len(out), np.nan)
    turning_events = wm_clean[wm_clean["wsmturning1"] == 1]
    if turning_events.empty:
        out["days_since_turning"] = pd.NA
    else:
        turning_times = turning_events.groupby("wsmEquipmentId", sort=False)["wsmUpdatedOn"].apply(lambda s: np.array(s.to_numpy(dtype="datetime64[ns]"), dtype="datetime64[ns]")).to_dict()
        for eid, group in indexed.groupby("equipment_key", sort=False):
            times = turning_times.get(eid)
            if times is None or len(times) == 0:
                continue
            rows = group["row"].to_numpy()
            ends = group["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
            pos = np.searchsorted(times, ends, side="right") - 1
            hit = pos >= 0
            if hit.any():
                days_since[rows[hit]] = (ends[hit] - times[pos[hit]]).astype("timedelta64[D]").astype(float)
        out["days_since_turning"] = days_since
    out["days_since_turning"] = out["days_since_turning"].astype("Float64")

    # --- Wheel register: profile and schedule at the endpoint wheel ---
    reg = wheel_register[["LwrId", "LwrWheelProfile", "LwrScheduleId", "LwrWsmSkidTurn"]].copy()
    reg["LwrId"] = pd.to_numeric(reg["LwrId"], errors="coerce").astype("Int64")
    wheel_info = out[["wheel_wr_id"]].rename(columns={"wheel_wr_id": "LwrId"}).merge(reg, on="LwrId", how="left")
    out["wheel_profile_2class"] = wheel_info["LwrWheelProfile"]
    out["wheel_schedule_id"] = wheel_info["LwrScheduleId"]
    out["wheel_skid_flag"] = wheel_info["LwrWsmSkidTurn"]

    # --- Home shed from the daily overdue ledger ---
    shed = daily_overdue[["LocoNumber", "EntryDate", "HomeShed"]].copy()
    shed["LocoNumber"] = shed["LocoNumber"].astype("string").str.strip()
    out["home_shed"] = _latest_at_or_before(shed, ["LocoNumber"], "EntryDate", out.rename(columns={"LomNumber": "LocoNumber"}), "HomeShed").astype("string")

    # --- Zone / division from the defect-history ledger ---
    def_zone = defects[["OldLocoId", "OldDateOccurance", "OldZone", "OldDivision"]].copy()
    def_zone["OldLocoId"] = pd.to_numeric(def_zone["OldLocoId"], errors="coerce").astype("Int64")
    out["defect_zone"] = _latest_at_or_before(def_zone, ["OldLocoId"], "OldDateOccurance", out.rename(columns={"interval_start_locomotive_id": "OldLocoId"}), "OldZone").astype("string")
    out["defect_division"] = _latest_at_or_before(def_zone, ["OldLocoId"], "OldDateOccurance", out.rename(columns={"interval_start_locomotive_id": "OldLocoId"}), "OldDivision").astype("string")

    # --- Wheel-age proxy: EmrDoR-anchored cascade (Q6), fallback EmrDoM then endpoint wsmProvDate ---
    master = equipment_master[["EmrId", "EmrDoR", "EmrDoM"]].copy()
    master["EmrId"] = pd.to_numeric(master["EmrId"], errors="coerce").astype("Int64")
    for col in ("EmrDoR", "EmrDoM"):
        master[col] = pd.to_datetime(master[col], errors="coerce")
    emr = out["wheelset_equipment_id"].rename("EmrId").to_frame()
    emr["EmrId"] = pd.to_numeric(emr["EmrId"], errors="coerce").astype("Int64")
    emr = emr.merge(master, on="EmrId", how="left")

    age_date = pd.Series(pd.NaT, index=out.index)
    date_source = pd.Series(pd.NA, index=out.index, dtype=object)
    interval_ends = pd.to_datetime(out["interval_end_timestamp"], errors="coerce").astype("datetime64[ns]")
    ok_dor = emr["EmrDoR"].notna() & (emr["EmrDoR"].dt.year > 1900) & (emr["EmrDoR"] <= interval_ends)
    age_date = age_date.where(~ok_dor, emr["EmrDoR"])
    date_source = date_source.mask(ok_dor, "EmrDoR")
    ok_dom = ~ok_dor & emr["EmrDoM"].notna() & (emr["EmrDoM"].dt.year > 1900) & (emr["EmrDoM"] <= interval_ends)
    age_date = age_date.where(~ok_dom, emr["EmrDoM"])
    date_source = date_source.mask(ok_dom, "EmrDoM")
    prov = joined["wsmProvDate"]
    ok_prov = ~ok_dor & ~ok_dom & prov.notna() & (prov.dt.year > 1900) & (prov <= interval_ends)
    age_date = age_date.where(~ok_prov, prov)
    date_source = date_source.mask(ok_prov, "wsmProvDate")

    out["wheel_age_days_proxy"] = (out["interval_end_timestamp"] - age_date).dt.total_seconds() / 86400.0
    out.loc[age_date.isna(), "wheel_age_days_proxy"] = pd.NA
    out["wheel_age_days_proxy"] = out["wheel_age_days_proxy"].astype("Float64")
    out["wheel_age_date_source"] = date_source

    out["interval_context_contract_version"] = INTERVAL_CONTEXT_VERSION
    return out


def build_interval_context_pipeline() -> dict[str, Path]:
    interval_path = GOLD_DIR / "inspection_intervals" / "v1.0" / "inspection_intervals_gold_b.parquet"
    wsm_path = BRONZE_DIR / "wheel_measurements.parquet"
    formation_path = BRONZE_DIR / "wheel_formation_templates.parquet"
    register_path = BRONZE_DIR / "loco_wheel_register.parquet"
    shed_path = BRONZE_DIR / "daily_overdue_loco_count.parquet"
    defects_path = BRONZE_DIR / "online_defects_log_history.parquet"
    master_path = BRONZE_DIR / "equipment_master_register.parquet"

    frame = build_interval_context(
        pd.read_parquet(interval_path),
        pd.read_parquet(wsm_path),
        pd.read_parquet(formation_path),
        pd.read_parquet(register_path),
        pd.read_parquet(shed_path),
        pd.read_parquet(defects_path),
        pd.read_parquet(master_path),
    )
    run_id = str(uuid4())
    output_path = _write_parquet(frame, GOLD_DIR / "interval_context" / INTERVAL_CONTEXT_VERSION / "inspection_interval_context.parquet")
    coverage = {column: {"non_null_rows": int(frame[column].notna().sum()), "coverage_pct": round(float(frame[column].notna().mean() * 100), 4)} for column in frame.columns if column not in {"interval_start_measurement_id", "interval_end_measurement_id", "interval_end_timestamp", "wheelset_equipment_id", "LomNumber", "interval_start_locomotive_id"}}
    report = {
        "run_id": run_id,
        "contract_version": INTERVAL_CONTEXT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "point_in_time_rule": "interval_end_timestamp; only source facts with business time at or before interval end",
        "input_sha256": {"intervals": _sha256(interval_path), "wheel_measurements": _sha256(wsm_path), "formation": _sha256(formation_path), "wheel_register": _sha256(register_path), "daily_overdue": _sha256(shed_path), "defects": _sha256(defects_path), "equipment_master": _sha256(master_path)},
        "rows": len(frame),
        "coverage": coverage,
    }
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = QUALITY_DIR / f"interval_context_{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return {"interval_context": output_path, "quality_report": report_path}


if __name__ == "__main__":
    for name, path in build_interval_context_pipeline().items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
