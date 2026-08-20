"""Phase 5 - Validate the ratio-derived limiting dimension against the recorded
Reason Of Turning (LwrPurpose decoded via WheelReadingPurpose).

Rationale
---------
At a turning the lathe removes material from the whole profile, so flange/root/tread
and diameter all drop together. The cause of the cut can only be attributed from the
PRE-TURN state. This study checks that our engineering assumption -

    limiting dimension = argmax(value / Wrpld_limit)

agrees with the shed's own recorded reason on the SLAM website
("Reason Of Turning" = LwrPurpose -> WheelReadingPurpose).

Inputs (Bronze)
---------------
- loco_wheel_register.parquet  : LwrId, LwrLocoId, LwrPurpose, LwrTurningType,
                                 LwrWsmSkidTurn, LwrWheelProfile, LwrScheduleId,
                                 LwrUpdatedOn
- wheel_measurements.parquet   : wsmId, wsmEquipmentId, wsmWRId, wsmW1EndType,
                                 wsmWheelSetPosition, wsmUpdatedOn, wsmturning1,
                                 wsmDia1/2, wsmFlange1/2, wsmRoot1/2, wsmThread1/2
- configs/limit_register_v1.json          : Wrpld limits (flange 3.0 / root 6.0 / tread 6.5)
- configs/wheel_reference_decode_v1.json  : WheelReadingPurpose decode map

Output
------
models/phase5/report/reason_of_turning_validation.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BRONZE = ROOT / "data" / "bronze"
OUT = ROOT / "models" / "phase5" / "report"

LIMITS = {"flange": 3.0, "root": 6.0, "tread": 6.5}
WEAR_COLS = {"flange": "wsmFlange1", "root": "wsmRoot1", "tread": "wsmThread1"}

# Reason codes that indicate a wear-dimension limit was the recorded driver.
WEAR_REASON_CODES = {3, 5, 7, 8}  # Flange / FW/RW / Root / Tread limit crossed
DIA_REASON_CODES = {9}            # Wheel Dia Matching
NOCUT_REASON_CODES = {0, 4, 11}   # none recorded / normal wear / others


def _decode_reason(raw: pd.Series) -> pd.Series:
    """Multi-valued code string -> list of decoded reason labels (kept as a list)."""
    with (ROOT / "configs" / "wheel_reference_decode_v1.json").open(encoding="utf-8") as fh:
        ref = json.load(fh)["wheel_reading_purpose"]
    def parse(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return []
        text = str(value).strip()
        if text == "" or text == "nan" or text == "0":
            return []
        codes = [c.strip() for c in text.split(",") if c.strip()]
        return [ref.get(c, c) for c in codes]
    return raw.map(parse)


def main() -> None:
    reg = pd.read_parquet(BRONZE / "loco_wheel_register.parquet")
    wm = pd.read_parquet(BRONZE / "wheel_measurements.parquet")
    keep = [
        "wsmId", "wsmEquipmentId", "wsmWRId", "wsmW1EndType", "wsmWheelSetPosition",
        "wsmUpdatedOn", "wsmturning1", "wsmProvDate",
        "wsmDia1", "wsmDia2", "wsmFlange1", "wsmFlange2", "wsmRoot1", "wsmRoot2",
        "wsmThread1", "wsmThread2",
    ]
    wm = wm[[c for c in keep if c in wm.columns]]
    for c in ["wsmId", "wsmEquipmentId", "wsmWRId", "wsmW1EndType", "wsmWheelSetPosition", "wsmturning1"]:
        wm[c] = pd.to_numeric(wm[c], errors="coerce")
    wm["wsmUpdatedOn"] = pd.to_datetime(wm["wsmUpdatedOn"], errors="coerce")
    wm = wm.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).sort_values(["wsmEquipmentId", "wsmUpdatedOn"])

    reg_cols = ["LwrId", "LwrLocoId", "LwrPurpose", "LwrTurningType", "LwrUpdatedOn"]
    reg = reg[[c for c in reg_cols if c in reg.columns]]
    reg["LwrId"] = pd.to_numeric(reg["LwrId"], errors="coerce")
    reg["LwrTurningType"] = pd.to_numeric(reg["LwrTurningType"], errors="coerce")

    # --- Turning events: next measurement flagged wsmturning == 1 is the post-cut read.
    # The PRE-turn state is the last measurement before it for that equipment/wheel.
    events = []
    for (eq, side), grp in wm.groupby(["wsmEquipmentId", "wsmW1EndType"], sort=False):
        arr = grp.sort_values("wsmUpdatedOn")
        turn_mask = arr["wsmturning1"].eq(1).to_numpy()
        for i in np.flatnonzero(turn_mask):
            if i == 0:
                continue  # no pre-turn measurement available
            pre = arr.iloc[i - 1]
            post = arr.iloc[i]
            events.append({
                "wsmEquipmentId": eq,
                "side": side,
                "turn_ts": post["wsmUpdatedOn"],
                "pre_dia": np.nanmean([pre["wsmDia1"], pre["wsmDia2"]]),
                "post_dia": np.nanmean([post["wsmDia1"], post["wsmDia2"]]),
                "pre_flange": np.nanmean([pre["wsmFlange1"], pre["wsmFlange2"]]),
                "pre_root": np.nanmean([pre["wsmRoot1"], pre["wsmRoot2"]]),
                "pre_tread": np.nanmean([pre["wsmThread1"], pre["wsmThread2"]]),
                "register_id": pre["wsmWRId"],
            })
    ev = pd.DataFrame(events)
    if ev.empty:
        raise RuntimeError("No turning events found in bronze wheel_measurements.")
    valid = ev.dropna(subset=["pre_root", "pre_flange", "pre_tread"]).copy()
    valid = valid[valid["register_id"].notna()]
    ev = valid

    # --- Ratio limiting dimension (argmax value/limit) on the pre-turn state ---
    norm = np.column_stack([
        ev["pre_flange"].to_numpy(dtype=float) / LIMITS["flange"],
        ev["pre_root"].to_numpy(dtype=float) / LIMITS["root"],
        ev["pre_tread"].to_numpy(dtype=float) / LIMITS["tread"],
    ])
    ok = np.isfinite(norm).all(axis=1)
    labels = np.empty(len(ev), dtype=object)
    labels[~ok] = None
    labels[ok] = np.take(["flange", "root", "tread"], np.nanargmax(norm[ok], axis=1))
    ev["limiting_dim_ratio"] = labels

    # --- Join recorded reason via the register row referenced by the pre-turn read ---
    reg["reason_parsed"] = _decode_reason(reg["LwrPurpose"])
    ev = ev.merge(reg[["LwrId", "LwrPurpose", "reason_parsed", "LwrTurningType"]],
                  left_on="register_id", right_on="LwrId", how="left")

    def classify_reason(row):
        codes = []
        raw = row["LwrPurpose"]
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            codes = []
        else:
            text = str(raw).strip()
            codes = [c.strip() for c in text.split(",") if c.strip()] if text and text != "nan" else []
        codes = [int(c) for c in codes if c.isdigit()]
        if not codes or codes == [0]:
            return "no_cut"          # none recorded / sentinel 0
        if any(c in WEAR_REASON_CODES for c in codes):
            return "wear"            # flange / FW-RW / root / tread limit recorded as driver
        if any(c in DIA_REASON_CODES for c in codes):
            return "dia"             # wheel-diameter matching
        return "other"

    ev["recorded_wear"] = ev.apply(classify_reason, axis=1)

    # --- Agreement: ratio-argmax vs recorded wear driver (iso-shed judgement) ---
    ev["recorded_wear_dim"] = np.where(
        ev["recorded_wear"] == "no_cut", "no_cut",
        np.where(ev["recorded_wear"] == "dia", "dia", ev["limiting_dim_ratio"]))
    if "LwrId" in ev.columns:
        ev = ev.drop(columns=["LwrId"])

    agreement = ev["limiting_dim_ratio"] == ev["recorded_wear_dim"]
    summary = {
        "n_turns_with_prestate": int(len(ev)),
        "recorded_reason_distribution": ev["reason_parsed"].explode().value_counts().head(15).to_dict(),
        "recorded_wear_class": ev["recorded_wear"].value_counts().to_dict(),
        "limiting_dim_ratio_distribution": ev["limiting_dim_ratio"].value_counts().to_dict(),
        "agreement_ratio_vs_recorded": {
            "overall_pct": round(float(agreement.mean() * 100), 2),
            "breakdown": {
                k: {"n": int((ev["recorded_wear"] == k).sum()),
                    "limit_dim": ev.loc[ev["recorded_wear"] == k, "limiting_dim_ratio"].value_counts().to_dict(),
                    "pct_with_recorded_wear_code": round(float((ev["recorded_wear"] == k).mean() * 100), 2)}
                for k in ["wear", "dia", "no_cut", "other"]
            },
        },
        "per_dimension": {
            dim: {
                "n_ratio_limiting": int((ev["limiting_dim_ratio"] == dim).sum()),
                "median_pre_mm": round(float(ev.loc[ev["limiting_dim_ratio"] == dim, f"pre_{dim}"].median()), 2),
                "pct_over_limit": round(float((ev.loc[ev["limiting_dim_ratio"] == dim, f"pre_{dim}"] > LIMITS[dim]).mean() * 100), 2),
            }
            for dim in LIMITS
        },
        "reason_by_limit_dim": {
            dim: ev.loc[ev["limiting_dim_ratio"] == dim, "recorded_wear"].value_counts().to_dict()
            for dim in ["flange", "root", "tread"]
        },
        "inputs": {
            "wheel_register": str((BRONZE / "loco_wheel_register.parquet").relative_to(ROOT)),
            "wheel_measurements": str((BRONZE / "wheel_measurements.parquet").relative_to(ROOT)),
            "limits": "configs/limit_register_v1.json",
            "decode": "configs/wheel_reference_decode_v1.json",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "reason_of_turning_validation.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()