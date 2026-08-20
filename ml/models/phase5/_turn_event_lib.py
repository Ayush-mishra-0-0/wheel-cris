"""Shared turn-event reconstruction for the Reason-of-Turning studies.

Identical logic for both `run_reason_of_turning_validation.py` and
`run_attribution_calibration.py`: for every measurement flagged `wsmturning == 1`
with a preceding measurement of the same equipment (axle) + wheel-end, capture:

  pre-turn state  (last measurement before the turn)
  post-turn state (the turning-flagged measurement)
  delta           (material removed)

For each such event we carry the source register reference of the PRE-turn read
(`register_id` = its wsmWRId) so the recorded Reason Of Turning (LwrPurpose) and the
turning shed / schedule can be joined without ambiguity.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BRONZE = ROOT / "data" / "bronze"

MEASUREMENT_KEEP = [
    "wsmId", "wsmEquipmentId", "wsmWRId", "wsmW1EndType", "wsmWheelSetPosition",
    "wsmUpdatedOn", "wsmturning1", "wsmProvDate",
    "wsmDia1", "wsmDia2", "wsmFlange1", "wsmFlange2", "wsmRoot1", "wsmRoot2",
    "wsmThread1", "wsmThread2",
]


def load_turn_events() -> pd.DataFrame:
    """Build the turn-event table from Bronze wheel measurements (see module doc)."""
    wm = pd.read_parquet(BRONZE / "wheel_measurements.parquet")
    wm = wm[[c for c in MEASUREMENT_KEEP if c in wm.columns]]
    for c in ["wsmId", "wsmEquipmentId", "wsmWRId", "wsmW1EndType", "wsmWheelSetPosition", "wsmturning1"]:
        wm[c] = pd.to_numeric(wm[c], errors="coerce")
    wm["wsmUpdatedOn"] = pd.to_datetime(wm["wsmUpdatedOn"], errors="coerce")
    wm = wm.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).sort_values(["wsmEquipmentId", "wsmUpdatedOn"])

    events = []
    for (eq, side), grp in wm.groupby(["wsmEquipmentId", "wsmW1EndType"], sort=False):
        arr = grp.sort_values("wsmUpdatedOn")
        turn_mask = arr["wsmturning1"].eq(1).to_numpy()
        for i in np.flatnonzero(turn_mask):
            if i == 0:
                continue
            pre = arr.iloc[i - 1]
            post = arr.iloc[i]
            events.append({
                "wheelset_equipment_id": eq,
                "side": side,
                "pre_ts": pre["wsmUpdatedOn"],
                "turn_ts": post["wsmUpdatedOn"],
                "pre_dia": np.nanmean([pre["wsmDia1"], pre["wsmDia2"]]),
                "post_dia": np.nanmean([post["wsmDia1"], post["wsmDia2"]]),
                "cut_dia": float(np.nanmean([pre["wsmDia1"], pre["wsmDia2"]])) - float(np.nanmean([post["wsmDia1"], post["wsmDia2"]])),
                "pre_flange": np.nanmean([pre["wsmFlange1"], pre["wsmFlange2"]]),
                "pre_root": np.nanmean([pre["wsmRoot1"], pre["wsmRoot2"]]),
                "pre_tread": np.nanmean([pre["wsmThread1"], pre["wsmThread2"]]),
                "register_id": pre["wsmWRId"],
            })
    ev = pd.DataFrame(events)
    if ev.empty:
        raise RuntimeError("No turning events found in bronze wheel_measurements.")
    return ev


def ratio_limiting_dimension(ev: pd.DataFrame, limits: dict) -> pd.DataFrame:
    """Attach the ratio-argmax limiting dimension on the pre-turn state (in place).

    limits: {"flange": 3.0, "root": 6.0, "tread": 6.5} (Wrpld, mm)
    """
    norm = np.column_stack([
        ev["pre_flange"].to_numpy(dtype=float) / limits["flange"],
        ev["pre_root"].to_numpy(dtype=float) / limits["root"],
        ev["pre_tread"].to_numpy(dtype=float) / limits["tread"],
    ])
    ok = np.isfinite(norm).all(axis=1)
    labels = np.empty(len(ev), dtype=object)
    labels[~ok] = None
    labels[ok] = np.take(["flange", "root", "tread"], np.nanargmax(norm[ok], axis=1))
    ev["limiting_dim_ratio"] = labels
    return ev


def load_register() -> pd.DataFrame:
    reg = pd.read_parquet(BRONZE / "loco_wheel_register.parquet")
    # retain raw columns referenced by both studies
    keep = ["LwrId", "LwrLocoId", "LwrPurpose", "LwrTurningType", "LwrWheelProfile",
            "LwrScheduleId", "LwrFuncLocId", "LwrUpdatedOn"]
    reg = reg[[c for c in keep if c in reg.columns]]
    reg["LwrId"] = pd.to_numeric(reg["LwrId"], errors="coerce")
    return reg