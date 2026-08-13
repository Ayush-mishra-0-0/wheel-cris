"""Phase 3 Step 0: audit what a recorded turning event represents.

This is intentionally a process/label audit, not a predictive model.  It uses
only frozen local source extracts and reports both the evidence available in
the data and the questions that cannot be answered without maintenance-owner
confirmation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_MEASUREMENTS = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
TIMELINE = ROOT / "data" / "gold" / "wheel_timeline_gold_b.parquet"
JOBCARDS = ROOT / "data" / "bronze" / "section_jobcards.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3" / "maintenance_process_audit"


def _valid_diameter(series: pd.Series) -> pd.Series:
    return series.between(1000.0, 1100.0)


def _jobcard_window_counts(event_days: pd.DataFrame, jobcards: pd.DataFrame) -> pd.DataFrame:
    """Count jobcards on the event day and within one calendar day by locomotive.

    This is an availability/context measure only: a jobcard has no wheelset key
    and its creation timestamp is not a confirmed maintenance completion time.
    """
    jobs = jobcards.copy()
    jobs["loco"] = pd.to_numeric(jobs["SejLocoId"], errors="coerce")
    jobs["day"] = pd.to_datetime(jobs["SejCreatedOn"], errors="coerce").dt.normalize()
    jobs = jobs.dropna(subset=["loco", "day"])
    jobs["loco"] = jobs["loco"].astype("int64")
    jobs["wheel_terms"] = jobs["SejRemarks"].fillna("").str.contains(
        r"wheel|turn|tyre|tire|flange|profile|skid", case=False, regex=True
    ).astype("int64")
    daily = jobs.groupby(["loco", "day"], as_index=False).agg(
        jobcards=("SejId", "size"), wheel_term_jobcards=("wheel_terms", "sum")
    )

    result = event_days.copy()
    result["jobcards_same_day"] = 0
    result["wheel_term_jobcards_same_day"] = 0
    result["jobcards_pm1_day"] = 0
    for loco, group in result.groupby("locomotive_id", sort=False):
        days = daily.loc[daily["loco"].eq(loco)].sort_values("day")
        if days.empty:
            continue
        jd = days["day"].to_numpy(dtype="datetime64[ns]")
        jc = days["jobcards"].to_numpy(dtype="int64")
        kw = days["wheel_term_jobcards"].to_numpy(dtype="int64")
        ed = group["event_day"].to_numpy(dtype="datetime64[ns]")
        left = np.searchsorted(jd, ed - np.timedelta64(1, "D"), side="left")
        right = np.searchsorted(jd, ed + np.timedelta64(1, "D"), side="right")
        exact_left = np.searchsorted(jd, ed, side="left")
        exact_right = np.searchsorted(jd, ed, side="right")
        result.loc[group.index, "jobcards_pm1_day"] = np.array(
            [jc[a:b].sum() for a, b in zip(left, right)], dtype="int64"
        )
        result.loc[group.index, "jobcards_same_day"] = np.array(
            [jc[a:b].sum() for a, b in zip(exact_left, exact_right)], dtype="int64"
        )
        result.loc[group.index, "wheel_term_jobcards_same_day"] = np.array(
            [kw[a:b].sum() for a, b in zip(exact_left, exact_right)], dtype="int64"
        )
    return result


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(
        RAW_MEASUREMENTS,
        columns=["wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmDia1", "wsmDia2",
                 "wsmturning1", "wsmturning2"],
    )
    raw = raw.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).copy()
    raw["equipment"] = raw["wsmEquipmentId"].astype("int64")
    raw["turn1"] = raw["wsmturning1"].eq(1)
    raw["turn2"] = raw["wsmturning2"].eq(1)
    raw = raw.sort_values(["equipment", "wsmUpdatedOn", "wsmId"])
    raw["next_turn1"] = raw.groupby("equipment", sort=False)["turn1"].shift(-1)
    raw["prev_turn1"] = raw.groupby("equipment", sort=False)["turn1"].shift(1)
    raw["prev_dia1"] = raw.groupby("equipment", sort=False)["wsmDia1"].shift(1)
    raw["prev_time"] = raw.groupby("equipment", sort=False)["wsmUpdatedOn"].shift(1)

    turn_rows = raw.loc[raw["turn1"]].copy()
    side_table = pd.crosstab(raw["turn1"], raw["turn2"])
    follow = pd.Series(np.select(
        [turn_rows["next_turn1"].eq(True), turn_rows["next_turn1"].eq(False)],
        ["followed_by_turn", "followed_by_nonturn"], default="last_measurement"
    )).value_counts().to_dict()
    turn_rows["event_day"] = turn_rows["wsmUpdatedOn"].dt.normalize()
    turn_days = turn_rows.drop_duplicates(["equipment", "event_day"])

    fresh = turn_rows.loc[turn_rows["prev_turn1"].ne(True)].copy()
    fresh["gap_days"] = (fresh["wsmUpdatedOn"] - fresh["prev_time"]).dt.total_seconds() / 86400
    fresh = fresh.loc[
        fresh["gap_days"].between(1, 400)
        & _valid_diameter(fresh["wsmDia1"])
        & _valid_diameter(fresh["prev_dia1"])
    ].copy()
    fresh["dia_change_at_flag_mm"] = fresh["wsmDia1"] - fresh["prev_dia1"]
    change = fresh["dia_change_at_flag_mm"]

    timeline = pd.read_parquet(
        TIMELINE,
        columns=["measurement_record_id", "wheelset_equipment_id", "measurement_timestamp",
                 "locomotive_id", "wsmturning1"],
    )
    timeline["event_day"] = pd.to_datetime(timeline["measurement_timestamp"]).dt.normalize()
    timeline["turn1"] = timeline["wsmturning1"].eq(1)
    event_timeline = timeline.loc[timeline["turn1"]].dropna(subset=["locomotive_id"]).copy()
    event_timeline["locomotive_id"] = event_timeline["locomotive_id"].astype("int64")
    event_days_loco = event_timeline.drop_duplicates(
        ["wheelset_equipment_id", "locomotive_id", "event_day"]
    )
    fleet_counts = event_days_loco.groupby(["locomotive_id", "event_day"])["wheelset_equipment_id"].nunique()
    event_days_loco["wheelsets_turned_same_loco_day"] = event_days_loco.set_index(
        ["locomotive_id", "event_day"]
    ).index.map(fleet_counts).astype("int64")
    event_days_loco = _jobcard_window_counts(
        event_days_loco[["wheelset_equipment_id", "locomotive_id", "event_day",
                         "wheelsets_turned_same_loco_day"]],
        pd.read_parquet(JOBCARDS, columns=["SejId", "SejLocoId", "SejCreatedOn", "SejRemarks"]),
    )

    metrics = {
        "source": {
            "raw_measurements": str(RAW_MEASUREMENTS.relative_to(ROOT)),
            "timeline": str(TIMELINE.relative_to(ROOT)),
            "jobcards": str(JOBCARDS.relative_to(ROOT)),
        },
        "turning_flag": {
            "measurement_rows": int(len(raw)),
            "turn1_rows": int(len(turn_rows)),
            "turn1_row_rate": float(len(turn_rows) / len(raw)),
            "distinct_turning_equipment_days": int(len(turn_days)),
            "same_day_duplicate_turning_rows": int(len(turn_rows) - len(turn_days)),
            "side_agreement_counts": {f"turn1_{a}_turn2_{b}": int(v) for (a, b), v in side_table.stack().items()},
            "next_measurement_pattern_after_turn1": {k: int(v) for k, v in follow.items()},
        },
        "measurement_at_new_turn_flag": {
            "n_valid_prior_measurement_pairs": int(len(fresh)),
            "median_dia_change_mm": float(change.median()),
            "mean_dia_change_mm": float(change.mean()),
            "share_dia_drop_gt_3mm": float((change < -3).mean()),
            "share_dia_gain_gt_3mm": float((change > 3).mean()),
            "share_abs_change_le_3mm": float((change.abs() <= 3).mean()),
        },
        "fleet_and_jobcard_context": {
            "turning_equipment_days_with_loco": int(len(event_days_loco)),
            "share_co_turned_same_locomotive_day": float((event_days_loco["wheelsets_turned_same_loco_day"] > 1).mean()),
            "median_wheelsets_turned_same_locomotive_day": float(event_days_loco["wheelsets_turned_same_loco_day"].median()),
            "share_with_jobcard_same_day": float((event_days_loco["jobcards_same_day"] > 0).mean()),
            "share_with_jobcard_within_pm1_day": float((event_days_loco["jobcards_pm1_day"] > 0).mean()),
            "share_with_wheel_term_jobcard_same_day": float((event_days_loco["wheel_term_jobcards_same_day"] > 0).mean()),
        },
        "interpretation": {
            "status": "INSUFFICIENT_TO_CONFIRM_ENGINEERING_TRIGGER",
            "reason": "The turning flag is a measurement-level outcome. Jobcards are locomotive-level, lack a wheelset key and action/reason code, and creation time is not maintenance completion time.",
        },
    }
    (OUTPUT / "maintenance_process_audit.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    m = metrics
    lines = [
        "# Phase 3 Step 0 — Maintenance Process Audit",
        "",
        "## Decision",
        "",
        "**Treat `wsmturning1` as an observed maintenance-realization target, not as directly observed engineering need.** It may reflect engineering condition, scheduled work, fleet-level action, and data-entry process.",
        "",
        "## What the data can establish",
        "",
        f"- `{m['turning_flag']['turn1_rows']:,}` turn-flagged measurement rows across `{m['turning_flag']['distinct_turning_equipment_days']:,}` distinct wheelset-days; `{m['turning_flag']['same_day_duplicate_turning_rows']:,}` rows are same-day duplicates.",
        f"- At a new turn flag, valid prior-measurement pairs have median diameter change {m['measurement_at_new_turn_flag']['median_dia_change_mm']:.2f} mm; {m['measurement_at_new_turn_flag']['share_dia_drop_gt_3mm']:.1%} drop by more than 3 mm and {m['measurement_at_new_turn_flag']['share_dia_gain_gt_3mm']:.1%} gain by more than 3 mm. The {m['measurement_at_new_turn_flag']['share_abs_change_le_3mm']:.1%} at <=3 mm are compatible with minimum-cut reprofiling and must not be used to invalidate the event flag.",
        f"- {m['fleet_and_jobcard_context']['share_co_turned_same_locomotive_day']:.1%} of linked turning wheelset-days co-occur with another turned wheelset on the same locomotive-day. This is evidence of possible fleet-level batching, not proof of its cause.",
        f"- A jobcard exists on the same locomotive-day for {m['fleet_and_jobcard_context']['share_with_jobcard_same_day']:.1%} of linked events and within ±1 day for {m['fleet_and_jobcard_context']['share_with_jobcard_within_pm1_day']:.1%}. This is temporal context only.",
        "",
        "## What the data cannot establish",
        "",
        "- The engineering criterion that triggered a turn: no wheelset-level reason code or first-limit-hit field is available.",
        "- Whether turning was scheduled, preventive, emergency, capacity-constrained, or discretionary.",
        "- A reliable completion time or a causal jobcard linkage: jobcards are locomotive-level and `SejCreatedOn` is creation time, not confirmed work completion.",
        "- Whether a non-turning record represents a healthy wheel versus an unserved wheel waiting for workshop capacity.",
        "",
        "## Engineering interpretation",
        "",
        "Wheel reprofiling is a multi-constraint action: the material removed can be set by the limiting flange/profile/defect condition, not by a fixed diameter reduction. Indian Railways training material describes intermediate worn-wheel profiles specifically to reduce metal removal. Therefore, diameter delta is unsuitable as a turning-signature test or as a sole health target. The later Wheel Health State must be a vector of measured margins, not a single diameter score.",
        "",
        "## Required domain-owner decisions before Target Specification v2",
        "",
        "1. Provide the authoritative turning/reprofiling decision rule and limits by wheel profile/type.",
        "2. Identify a wheelset-level maintenance action/reason/completion source, or formally state that none exists.",
        "3. Define whether `wsmturning1` is recorded before, during, or after the physical turning operation.",
        "4. Define replacement versus reprofiling and planned versus unscheduled maintenance semantics.",
        "5. Confirm whether multi-wheel same-locomotive actions are policy batching and how they should be represented.",
        "",
        "## Gate",
        "",
        "Proceed with two explicitly separate constructs: (1) `wsmturning1` as an **operational maintenance-realization** target, and (2) a rule-based, uncertainty-labelled Wheel Health State as the proxy for latent engineering need. Do not present the former as direct ground truth for the latter; where richer maintenance records are unavailable, report the policy/scheduling limitation in every model result.",
    ]
    (OUTPUT / "maintenance_process_audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
