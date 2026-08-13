"""Phase 3 audit of recorded turning realizations and observation windows.

The audit does not silently select a deduplication rule.  It quantifies repeated
turn flags and horizon follow-up so Target Specification v2 can choose a rule
with evidence and disclose informative-censoring limitations.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3" / "event_censoring_audit"
HORIZONS = (30, 90, 180, 365)


def main() -> None:
    df = pd.read_parquet(SOURCE, columns=["wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmturning1", "wsmturning2", "wsmProvDate"])
    df = df.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).copy()
    df["equipment"] = df["wsmEquipmentId"].astype("int64")
    df["time"] = pd.to_datetime(df["wsmUpdatedOn"])
    df["turn1"] = df["wsmturning1"].eq(1)
    df["turn2"] = df["wsmturning2"].eq(1)
    df = df.sort_values(["equipment", "time", "wsmId"])
    turns = df.loc[df["turn1"], ["equipment", "time", "wsmId", "turn2"]].copy()
    turns["day"] = turns["time"].dt.normalize()
    turns["prev_turn_time"] = turns.groupby("equipment", sort=False)["time"].shift(1)
    turns["gap_days"] = (turns["time"] - turns["prev_turn_time"]).dt.total_seconds() / 86400
    gap_bucket = pd.cut(turns["gap_days"], bins=[-0.001, 0, 7, 30, 180, np.inf], labels=["same_day", "1_7d", "8_30d", "31_180d", "gt_180d"])
    gap_labels = gap_bucket.astype("string").fillna("first_turn_for_equipment")
    gaps = gap_labels.value_counts(dropna=False).to_dict()

    event_days = turns.drop_duplicates(["equipment", "day"]).sort_values(["equipment", "day"])
    last_time = df.groupby("equipment", sort=False)["time"].max().rename("observation_end")
    scored = df[["equipment", "time", "wsmId"]].copy()
    scored["observation_end"] = scored["equipment"].map(last_time)
    scored["followup_days"] = (scored["observation_end"] - scored["time"]).dt.total_seconds() / 86400
    global_end = df["time"].max()
    end_gap_days = (global_end - last_time).dt.total_seconds() / 86400

    event_arrays = {equipment: group["day"].to_numpy(dtype="datetime64[ns]") for equipment, group in event_days.groupby("equipment", sort=False)}
    outcomes = []
    for horizon in HORIZONS:
        eligible = scored.loc[scored["followup_days"] >= horizon, ["equipment", "time"]]
        event_n = 0
        for equipment, group in eligible.groupby("equipment", sort=False):
            dates = event_arrays.get(equipment)
            if dates is None:
                continue
            start = group["time"].to_numpy(dtype="datetime64[ns]")
            left = np.searchsorted(dates, start, side="right")
            right = np.searchsorted(dates, start + np.timedelta64(horizon, "D"), side="right")
            event_n += int((right > left).sum())
        outcomes.append({"horizon_days": horizon, "eligible_states": int(len(eligible)), "eligible_fraction": float(len(eligible) / len(scored)), "realized_turning_within_horizon": event_n, "event_rate": float(event_n / len(eligible)) if len(eligible) else None})

    metrics = {
        "source": str(SOURCE.relative_to(ROOT)),
        "global_measurement_end": global_end.isoformat(),
        "rows_with_attributable_equipment_and_time": int(len(df)),
        "turning_rows": int(len(turns)),
        "distinct_turning_equipment_days": int(len(event_days)),
        "turn_flag_gap_buckets": {str(k): int(v) for k, v in gaps.items()},
        "turn_side_agreement": {"turn1_rows_with_turn2": int(turns["turn2"].sum()), "turn1_rows_without_turn2": int((~turns["turn2"]).sum())},
        "observation_end": {"n_equipment": int(last_time.size), "median_days_before_global_end": float(end_gap_days.median()), "share_equipment_last_seen_more_than_365_days_before_global_end": float((end_gap_days > 365).mean()), "share_equipment_last_seen_more_than_30_days_before_global_end": float((end_gap_days > 30).mean())},
        "horizon_followup": outcomes,
        "decision": "CENSORING_RULE_NOT_APPROVED",
        "reason": "Per-equipment last measurement is observable, but may reflect withdrawal, reassignment, or missing capture rather than administrative study end. It cannot be assumed non-informative without owner confirmation.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "event_censoring_audit.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 3 — Event & Censoring Audit",
        "",
        "## Decision",
        "",
        "**Do not train a survival model yet.** The recorded turn flag is usable as a candidate maintenance-realization signal, but the duplicate-event rule and censoring mechanism require explicit approval.",
        "",
        "## Recorded-event evidence",
        "",
        f"- {len(turns):,} `wsmturning1` rows reduce to {len(event_days):,} distinct equipment-days after same-day deduplication.",
        f"- Side-2 agrees on {turns['turn2'].mean():.1%} of turn-1 rows; disagreement must remain an event-quality flag.",
        "- Consecutive flagged-row gaps are reported in `event_censoring_audit.json`; a cross-day cluster threshold is deliberately not inferred by this audit.",
        "",
        "## Observation-window evidence",
        "",
        f"- Latest source measurement: {global_end.date().isoformat()}. The median equipment observation end is {end_gap_days.median():.0f} days earlier.",
        f"- {((end_gap_days > 30).mean()):.1%} of equipment are last seen more than 30 days before the global end; {((end_gap_days > 365).mean()):.1%} are last seen more than 365 days earlier.",
        "",
        "| Horizon | Eligible states | Eligible % | Realized turnings | Event rate |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in outcomes:
        lines.append(f"| {row['horizon_days']} d | {row['eligible_states']:,} | {row['eligible_fraction']:.1%} | {row['realized_turning_within_horizon']:,} | {row['event_rate']:.3%} |")
    lines += [
        "",
        "## Required decisions",
        "",
        "1. Approve event deduplication: same equipment-day only, or a longer post-turning cluster window with a documented operational basis.",
        "2. Define whether a missing future measurement means administrative end of observation, reassignment/withdrawal, or unknown follow-up.",
        "3. Identify whether replacement/provision events should compete with, censor, or be included in maintenance realization.",
        "4. Approve the minimum event count and follow-up coverage required before each horizon is reported.",
        "",
        "## Provisional safe use",
        "",
        "Until the decisions above, a rolling binary benchmark may use only fixed-horizon labels with demonstrated follow-up for every negative example. Survival fitting and claims about maintenance RUL remain blocked.",
    ]
    (OUTPUT / "event_censoring_audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
