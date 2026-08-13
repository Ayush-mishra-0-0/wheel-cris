"""P0.2 fix step 1 - what do the missed >= threshold dia up-jumps represent?

The audit proved ~52% of >= 20mm consecutive dia up-jumps are NOT flagged as
turn_event/replacement by the serving boundary heuristic. Before adding a new
rule we must know what those jumps ARE:

  - a real wheel replacement missed because wsmProvDate was NaN on the pre row
    (serving prov_changed requires shift().notna())
  - a wheel-age reset missed by the strict (age<10 & prev>90) rule
  - a turning that failed the dia_cut<=25mm / flange-root-restore gate
  - an axle/position swap (only one physical wheel changed)
  - a side-swap (wsmDia1/wsmDia2 exchanged)
  - measurement error / one-off artifact (post level NOT maintained)

Every jump is profiled; results are written to
ml/models/experiments/v5/replacement_candidates_validation.json.

Run (repo root):
  & "<repo>\\ayush\\Scripts\\python.exe" ml\\models\\validate_replacement_candidates.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.phase5.dashboard.backend.features import load_wes  # noqa: E402

OUT = ROOT / "models" / "experiments" / "v5" / "replacement_candidates_validation.json"
THRESHOLD_MM = 20.0
POST_CONSISTENT_TOL_MM = 10.0
POST_CONSISTENT_N = 2


def profile_missed_jumps(wes: pd.DataFrame, thr: float) -> list[dict]:
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    ws = wes["wheelset_equipment_id"].to_numpy()
    dia = wes["mean_wsmDia"].to_numpy(dtype=float)
    flagged = wes["turn_event"].to_numpy(bool) | wes["replacement"].to_numpy(bool)

    # raw fields at jump row (i) and pre row (i-1)
    prov = pd.to_datetime(wes["wsmProvDate"]).to_numpy(dtype="datetime64[us]")
    prov_num = prov.astype("int64").astype(float)
    prov_num[prov_num == -9223372036854775808.0] = np.nan
    age = wes["wheel_age_days_proxy"].to_numpy(dtype=float)
    turn_rec = wes["turning_record_at_measurement"].to_numpy()
    turn_rec = np.where(turn_rec == 1, 1, 0)
    prof1 = wes["wheel_profile_2class"].to_numpy()
    lomo = wes["LomNumber"].to_numpy()
    loco = wes["locomotive_id"].to_numpy()
    d1 = wes["wsmDia1"].to_numpy(dtype=float)
    d2 = wes["wsmDia2"].to_numpy(dtype=float)
    ts = wes["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    seg = wes["seg_id"].to_numpy()

    n = len(wes)
    same_ws = ws[1:] == ws[:-1]
    jump = dia[1:] - dia[:-1]
    up_idx = np.flatnonzero(same_ws & (jump >= thr) & ~flagged[1:])

    rows: list[dict] = []
    for i in up_idx:
        j = i + 1
        r = {
            "wheelset": int(ws[j]),
            "pre_idx": int(i),
            "jump_idx": int(j),
            "jump_mm": round(float(dia[j] - dia[i]), 3),
            "pre_dia_mm": round(float(dia[i]), 3),
            "post_dia_mm": round(float(dia[j]), 3),
            "gap_days": round(float((ts[j] - ts[i]) / np.timedelta64(1, "D")), 3),
            "prov_date_changed": bool(np.isfinite(prov_num[i]) and np.isfinite(prov_num[j])
                                      and prov_num[j] != prov_num[i]),
            "prov_date_became_valid": bool(np.isnan(prov_num[i]) and np.isfinite(prov_num[j])),
            "prov_date_lost": bool(np.isfinite(prov_num[i]) and np.isnan(prov_num[j])),
            "age_reset_strict": bool(age[j] < 10 and age[i] > 90),
            "age_reset_soft": bool(np.isfinite(age[i]) and np.isfinite(age[j])
                                   and age[j] < age[i]),
            "age_pre": round(float(age[i]), 3) if np.isfinite(age[i]) else None,
            "age_post": round(float(age[j]), 3) if np.isfinite(age[j]) else None,
            "turning_record": bool(turn_rec[j] == 1),
            "side1_jump_mm": round(float(d1[j] - d1[i]), 3) if np.isfinite(d1[i]) and np.isfinite(d1[j]) else None,
            "side2_jump_mm": round(float(d2[j] - d2[i]), 3) if np.isfinite(d2[i]) and np.isfinite(d2[j]) else None,
            "both_sides": bool(np.isfinite(d1[i]) and np.isfinite(d1[j])
                               and np.isfinite(d2[i]) and np.isfinite(d2[j])
                               and d1[j] - d1[i] >= thr and d2[j] - d2[i] >= thr),
            "profile_changed": bool(prof1[i] != prof1[j]),
            "profile_pre": str(prof1[i]) if pd.notna(prof1[i]) else None,
            "profile_post": str(prof1[j]) if pd.notna(prof1[j]) else None,
            "locomotive_changed": bool(loco[i] != loco[j]),
            "lom_changed": bool(lomo[i] != lomo[j]),
            "same_segment": bool(seg[i] == seg[j]),
        }
        # post-jump level consistency: are the next POST_CONSISTENT_N measurements
        # (same wheelset) still near the new (higher) level?
        kept = 0
        first_high = 0.0
        for k in range(j + 1, n):
            if ws[k] != ws[j]:
                break
            if not np.isfinite(dia[k]):
                continue
            kept += 1
            if kept == 1:
                first_high = round(float(dia[k] - dia[j]), 3)
            if kept >= POST_CONSISTENT_N:
                r["post_consistent"] = bool(
                    (dia[k] >= dia[j] - POST_CONSISTENT_TOL_MM)
                    and (dia[k] <= dia[j] + POST_CONSISTENT_TOL_MM))
                r["post_level_drift_mm"] = first_high
                break
        if kept < POST_CONSISTENT_N:
            r["post_consistent"] = None
            r["post_level_drift_mm"] = first_high if kept else None
        rows.append(r)
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    arr = np.array([r["jump_mm"] for r in rows])
    gd = np.array([r["gap_days"] for r in rows])
    flags = {
        "prov_date_changed": sum(1 for r in rows if r["prov_date_changed"]),
        "prov_became_valid": sum(1 for r in rows if r["prov_date_became_valid"]),
        "prov_lost": sum(1 for r in rows if r["prov_date_lost"]),
        "age_reset_strict": sum(1 for r in rows if r["age_reset_strict"]),
        "age_reset_soft": sum(1 for r in rows if r["age_reset_soft"]),
        "turning_record": sum(1 for r in rows if r["turning_record"]),
        "both_sides": sum(1 for r in rows if r["both_sides"]),
        "profile_changed": sum(1 for r in rows if r["profile_changed"]),
        "locomotive_changed": sum(1 for r in rows if r["locomotive_changed"]),
        "lom_changed": sum(1 for r in rows if r["lom_changed"]),
        "same_segment": sum(1 for r in rows if r["same_segment"]),
        "post_consistent_true": sum(1 for r in rows if r["post_consistent"] is True),
        "post_consistent_false": sum(1 for r in rows if r["post_consistent"] is False),
        "post_consistent_na": sum(1 for r in rows if r["post_consistent"] is None),
    }
    any_signal = sum(1 for r in rows
                     if r["prov_date_changed"] or r["prov_date_became_valid"]
                     or r["age_reset_soft"] or r["turning_record"]
                     or r["lom_changed"])
    return {
        "n": n,
        "jump_mm_median": round(float(np.median(arr)), 3),
        "jump_mm_p10_p90": [round(float(np.percentile(arr, 10)), 3),
                            round(float(np.percentile(arr, 90)), 3)],
        "gap_days_median": round(float(np.median(gd)), 3),
        "flags": flags,
        "any_replacement_signal_pct": round(any_signal / n * 100, 2),
        "post_consistent_pct": round(
            sum(1 for r in rows if r["post_consistent"] is True) / n * 100, 2),
    }


def main() -> None:
    print("Loading WES v3 (serving boundary logic) ...")
    wes = load_wes()
    print(f"Profiling missed >= {THRESHOLD_MM:g}mm dia up-jumps ...")
    rows = profile_missed_jumps(wes, THRESHOLD_MM)

    summ = summarize(rows)
    # cross-tab: which signals co-occur
    sig = pd.DataFrame(rows)
    report = {
        "task": "P0.2 replacement-candidate validation",
        "boundary_logic": "models.phase5.dashboard.backend.features._boundaries (serving-exact)",
        "threshold_mm": THRESHOLD_MM,
        "summary": summ,
        "cross_tabs": {
            "age_reset_soft_x_prov_signal": int(
                ((sig["age_reset_soft"] | sig["prov_date_changed"]
                  | sig["prov_date_became_valid"])).sum()),
            "post_consistent_true_x_any_signal": int(
                ((sig["post_consistent"] == True) &  # noqa: E712
                 (sig["age_reset_soft"] | sig["prov_date_changed"]
                  | sig["prov_date_became_valid"])).sum()),
            "post_consistent_true_x_no_signal": int(
                ((sig["post_consistent"] == True) &  # noqa: E712
                 ~(sig["age_reset_soft"] | sig["prov_date_changed"]
                   | sig["prov_date_became_valid"])).sum()),
        },
        "sample": rows[:25],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summ, indent=2, default=str))
    print(f"\nWrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
