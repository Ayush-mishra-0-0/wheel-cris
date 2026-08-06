"""Phase 3 - Target Eligibility Matrix (Artifact 4).

For each fixed horizon (30/90/180/365 d) the report answers, at the granularity
of one attributable measurement state:

    Eligible            = follow_up_days >= horizon  OR  event within horizon
    Event               = a recorded turning realisation occurred within horizon
    Censored (non-event)= follow_up_days >= horizon  AND  no event within horizon
    Unknown follow-up   = follow_up_days <  horizon  AND  no event within horizon

Eligibility deliberately does NOT require a full horizon on every row.  Rows whose
event is observed within the horizon are reportable even when the administrative
window is short.  Only rows where the horizon outcome is genuinely unknowable
(follow-up too short AND no event) are excluded as UNKNOWN.  This removes label
noise from wheels whose follow-up window is not demonstrated, per the tightened
cohort definition authorised for the fixed-horizon benchmark.

Events use the same equipment-day deduplication as the Event & Censoring Audit
(duplicate same-day flags on one equipment collapse to a single event day).
"""  # noqa: E501
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3" / "target_eligibility"
HORIZONS = (30, 90, 180, 365)


def _event_days_by_equipment(turns: pd.DataFrame) -> dict[int, np.ndarray]:
    event_days = turns.drop_duplicates(["equipment", "day"])
    return {
        equipment: group["day"].to_numpy(dtype="datetime64[ns]")
        for equipment, group in event_days.groupby("equipment", sort=False)
    }


def main() -> None:
    df = pd.read_parquet(
        SOURCE,
        columns=["wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmturning1", "wsmProvDate"],
    )
    df = df.dropna(subset=["wsmEquipmentId", "wsmUpdatedOn"]).copy()
    df["equipment"] = df["wsmEquipmentId"].astype("int64")
    df["time"] = pd.to_datetime(df["wsmUpdatedOn"])
    df["turn1"] = df["wsmturning1"].eq(1)
    df = df.sort_values(["equipment", "time", "wsmId"])

    turns = df.loc[df["turn1"], ["equipment", "time", "wsmId"]].copy()
    turns["day"] = turns["time"].dt.normalize()
    event_days = _event_days_by_equipment(turns)

    last_time = df.groupby("equipment", sort=False)["time"].max()
    scored = df[["equipment", "time", "wsmId"]].copy()
    scored["observation_end"] = scored["equipment"].map(last_time)
    scored["followup_days"] = (scored["observation_end"] - scored["time"]).dt.total_seconds() / 86400

    # Per-row lookup of whether an event day falls strictly inside (t, t+horizon].
    equipment_codes = scored["equipment"].to_numpy()
    time_values = scored["time"].to_numpy(dtype="datetime64[ns]")
    event_lookup = {int(e): a for e, a in event_days.items()}

    rows = {"total_states": int(len(scored)), "distinct_equipment": int(len(last_time))}
    matrix = []
    for horizon in HORIZONS:
        event_within = np.zeros(len(scored), dtype=bool)
        for equipment, dates in event_lookup.items():
            mask = equipment_codes == equipment
            if not mask.any():
                continue
            start = time_values[mask]
            left = np.searchsorted(dates, start, side="right")
            right = np.searchsorted(dates, start + np.timedelta64(horizon, "D"), side="right")
            event_within[mask] = right > left

        full_window = scored["followup_days"].to_numpy() >= horizon
        is_event = event_within
        is_censored = (~is_event) & full_window
        is_unknown = (~is_event) & (~full_window)
        eligible = is_event | full_window  # events observed + non-events with full window

        matrix.append(
            {
                "horizon_days": horizon,
                "eligible_states": int(eligible.sum()),
                "eligible_fraction": float(eligible.mean()),
                "events": int(is_event.sum()),
                "event_rate_of_eligible": float(is_event.sum() / max(eligible.sum(), 1)),
                "censored_non_event": int(is_censored.sum()),
                "unknown_followup": int(is_unknown.sum()),
                "unknown_fraction": float(is_unknown.mean()),
            }
        )
        del event_within

    rows["horizons"] = matrix
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "target_eligibility.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )

    table = pd.DataFrame(matrix)
    table.to_csv(OUTPUT / "target_eligibility_matrix.csv", index=False)

    lines = [
        "# Target Eligibility Matrix v1",
        "",
        "**Decision basis:** a horizon benchmark is reportable only where its",
        "`Eligible` cohort is large enough and its `Unknown follow-up` share is small",
        "enough to be disclosed. Eligibility follows the tightened cohort definition",
        "(event within horizon **or** full demonstrated follow-up), so every `Eligible`",
        "row has a knowable horizon label.",
        "",
        "| Horizon | Eligible rows | Eligible % | Events | Event rate | Censored (non-event) | Unknown follow-up | Unknown % |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in matrix:
        lines.append(
            f"| {r['horizon_days']} d | {r['eligible_states']:,} | {r['eligible_fraction']:.1%} "
            f"| {r['events']:,} | {r['event_rate_of_eligible']:.3%} | "
            f"{r['censored_non_event']:,} | {r['unknown_followup']:,} | {r['unknown_fraction']:.1%} |"
        )
    lines += [
        "",
        "## Reading the matrix",
        "",
        "- **Eligible** = rows with a knowable outcome: event realised within the",
        "  horizon, or at least `horizon` days of observed follow-up with no event.",
        "- **Events** = recorded turnings realised within the horizon (equipment-day",
        "  deduplicated).",
        "- **Censored (non-event)** = full observed window with no realised event; the",
        "  label is a demonstrated non-event, not an absence of record.",
        "- **Unknown follow-up** = observation window shorter than the horizon and no",
        "  event recorded; the horizon label is genuinely unknowable and these rows are",
        "  excluded from the eligible cohort for that horizon.",
        "",
        "## Reportability",
        "",
        "Use this matrix to decide which horizons are scientifically reportable, and to",
        "disclose the excluded (unknown) share per horizon before any binary benchmark",
        "is trained.",
    ]
    (OUTPUT / "target_eligibility_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
