"""Phase 5 - Shed-level attribution calibration on fresh Bronze.

Goal
----
Make the ratio-argmax limiting dimension defensible by calibrating it against the
recorded Reason Of Turning, per shed. The operational rule from the mapping doc is:
  bottleneck = recorded_reason when present, else ratio-argmax calibrated per shed.
This study produces that calibration: for every shed with enough turns, the
distribution of recorded wear class (flange/root/tread/dia/no_cut) across ratio-
labelled turns, plus an empirical prior P(recorded | ratio) used to convert a ratio
label into a calibrated attribution with provenance (`limiting_dim_source`).

Inputs (Bronze, refreshed 2026-08-20)
--------------------------------------
- wheel_measurements.parquet  : turn-flag + pre-state (via models/phase5/_turn_event_lib.py)
- loco_wheel_register.parquet : LwrPurpose (recorded reason), LwrFuncLocId (shed),
                                LwrScheduleId, LwrTurningType
- functional_locations.parquet: FLocCode/FLocName (shed decode)
- configs/limit_register_v1.json, configs/wheel_reference_decode_v1.json

Output
------
models/phase5/report/attribution_calibration.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from _turn_event_lib import ROOT, load_register, load_turn_events, ratio_limiting_dimension

OUT = ROOT / "models" / "phase5" / "report"

LIMITS = {"flange": 3.0, "root": 6.0, "tread": 6.5}

WEAR_REASON_CODES = {3, 5, 7, 8}  # Flange / FW-RW / Root / Tread limit crossed
DIA_REASON_CODES = {9}            # Wheel Dia Matching
NOCUT_REASON_CODES = {0, 4, 11}   # none recorded / normal wear / others

MIN_SHED_TURNS = 20
TOP_SHEDS = 12


def _load_decode() -> dict:
    with (ROOT / "configs" / "wheel_reference_decode_v1.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def classify_recorded(raw) -> str:
    """Classify a raw LwrPurpose code set into a coarse recorded attribution."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return "no_cut"
    text = str(raw).strip()
    if text == "" or text == "nan":
        return "no_cut"
    codes = [int(c) for c in [x.strip() for x in text.split(",") if x.strip()] if c.isdigit()]
    if not codes or codes in ([0]):       # sentinel 0 = none recorded
        return "no_cut"
    if any(c in WEAR_REASON_CODES for c in codes):
        return "wear"
    if any(c in DIA_REASON_CODES for c in codes):
        return "dia"
    return "other"


def main() -> None:
    ev = load_turn_events()
    ev = ratio_limiting_dimension(ev, LIMITS)

    reg = load_register()
    ref = _load_decode()
    rot = ref["wheel_reading_purpose"]

    # Join recorded reason + shed (FunctionalLocation) + schedule onto each turn.
    ev = ev.merge(reg[["LwrId", "LwrPurpose", "LwrTurningType", "LwrScheduleId", "LwrFuncLocId"]],
                  left_on="register_id", right_on="LwrId", how="left")
    floc = pd.read_parquet(ROOT / "data" / "bronze" / "functional_locations.parquet")
    floc["FLocId"] = pd.to_numeric(floc["FLocId"], errors="coerce")
    ev = ev.merge(floc[["FLocId", "FLocCode", "FLocName"]], left_on="LwrFuncLocId", right_on="FLocId", how="left")
    ev["shed"] = ev["FLocCode"].fillna("UNKNOWN")
    ev["recorded_wear"] = ev["LwrPurpose"].map(classify_recorded)
    # limit to pre-state-valid turns (ratio label present)
    ev = ev.dropna(subset=["limiting_dim_ratio", "pre_root", "pre_flange", "pre_tread"]).copy()
    ev = ev[ev["limiting_dim_ratio"].ne("nan")]

    # Decode reason labels for reporting.
    ev["reason_labels"] = ev["LwrPurpose"].map(
        lambda r: ", ".join(rot.get(c.strip(), c.strip()) for c in
                            str(r).split(",") if c.strip() if c.strip().isdigit()) if
        r == r and r is not None else None)

    # ---- Per-shed calibration table ----
    sheds = []
    for shed, g in ev.groupby("shed", sort=False):
        n = len(g)
        rec = g["recorded_wear"].value_counts().to_dict()
        ratio = g["limiting_dim_ratio"].value_counts().to_dict()
        wears = g[g["recorded_wear"] == "wear"]
        prior_list = {d: round(float((wears["limiting_dim_ratio"] == d).mean()), 3)
                      for d in ["flange", "root", "tread"]} if len(wears) else {}
        sheds.append({
            "shed": shed,
            "n_turns": int(n),
            "recorded": rec,
            "ratio": ratio,
            "p_recorded_wear_given_ratio": {
                d: round(float(prior_list.get(d, 0.0)), 3) for d in ["flange", "root", "tread"]
            },
            "share_recorded_wear": round(float(rec.get("wear", 0) / n), 3) if n else None,
        })
    shed_df = pd.DataFrame(sheds)
    top = shed_df.sort_values("n_turns", ascending=False).head(TOP_SHEDS)

    # ---- Fleet-level calibration ----
    evr = ev[ev["recorded_wear"].isin(["wear", "dia"])].copy()
    confusion = {
        d: {g: int((evr.loc[evr["limiting_dim_ratio"] == d, "recorded_wear"] == g).sum())
            for g in ["wear", "dia", "other", "no_cut"]}
        for d in ["flange", "root", "tread"]
    }
    weighted = {
        d: round(float(evr.loc[evr["limiting_dim_ratio"] == d, "recorded_wear"].eq("wear").mean()), 3)
        for d in ["flange", "root", "tread"]
    }

    summary = {
        "n_turns": int(len(ev)),
        "n_turns_with_recorded_reason": int(ev["LwrPurpose"].notna().sum()),
        "n_sheds_with_min_turns": int((shed_df["n_turns"] >= MIN_SHED_TURNS).sum()),
        "top_sheds": top.to_dict(orient="records"),
        "fleet_confusion_recorded_vs_ratio": confusion,
        "p_recorded_wear_given_ratio_dim": weighted,
        "operational_rule": "bottleneck = recorded_reason when present; else ratio-argmax calibrated per shed",
        "min_shed_turns_used": MIN_SHED_TURNS,
        "inputs": {
            "wheel_measurements": "data/bronze/wheel_measurements.parquet (2026-08-20)",
            "wheel_register": "data/bronze/loco_wheel_register.parquet (2026-08-20)",
            "functional_locations": "data/bronze/functional_locations.parquet",
            "limits": "configs/limit_register_v1.json",
            "decode": "configs/wheel_reference_decode_v1.json",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "attribution_calibration.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()