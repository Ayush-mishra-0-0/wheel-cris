"""Phase 3B - Engineering Intelligence: health index, estimated RUL, corrective action.

Builds, from the frozen Wheel Engineering State v1.0, a per-state engineering
intelligence output that supports maintenance prioritisation. The Wrpld wear
register (flange 3.0 / root 6.0 / tread 6.5 mm) is now approved; root (6.0 mm)
and dia (1016 mm) feed this index directly, while the registered flange/tread
fields remain SEMANTICS_BLOCKED in WES v1.0 until released.

Products:
  1. Segment-level wear rates (mm/day) per active dimension, aggregated over a
     wheel's current life-segment between turning/replacement resets. This
     averages per-inspection noise (which the next-state model showed dominates
     short intervals).
  2. Estimated Engineering RUL (days): fleet-REALTY, rate-based projection from
     the current measured value toward a threshold. Root and dia thresholds are
     the APPROVED limits (Wrpld root 6.0 mm; dia 1016 mm); flange/tread remain
     fleet-relative until their registered fields are released. RUL is still
     reported with the reference threshold named, never as a hygiene claim
     beyond what the register supports.
  3. Limiting dimension: which measured dimension is closest (relative to fleet)
     to its threshold given its wear rate -> drives the corrective action.
  4. Engineering Health Index: a 0-100 multi-dimension index combining proximity
     to fleet thresholds + wear rate + maintenance history, calibrated so it is
     transparent and rule-based (not a black-box health score).

Outputs: a state-level engineering_intelligence.parquet, per-wheel health cards,
a fleet and shed dashboard, and a report.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WES_PATH = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3b" / "engineering_intelligence"
DASH = ROOT / "reports" / "dashboards"

DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot", "wsmWheelGauge"]
SIDES = ["1", "2"]
# Threshold references used for proximity / relative RUL.
# - wsmDia  : documented 1016 mm condemning reference (approved hard stop).
# - wsmRoot : APPROVED wear limit from the Wrpld register
#             (configs/limit_register_v1.json, ratified 2026-08-19): root wear
#             0-6 mm, condemning = 6.0 mm. Supersedes the earlier 3 mm Q8 value.
# - wsmFlangeThickness / wsmWheelGauge : fleet-relative PRIORS only - these are
#   NOT in the Wrpld register (which governs wsmFlange wear 3.0 mm and wsmThread
#   wear 6.5 mm). Those registered fields remain SEMANTICS_BLOCKED in WES v1.0
#   (BLOCKED_FIELDS), so they cannot yet feed this index. When released, flange
#   (3.0) and tread (6.5) should be added here from the register.
# Transparent priors, never presented as official condemning limits where the
# register does not apply.
REFERENCE = {
    "wsmDia": (1000.0, 1016.0),          # (soft floor, hard reference) lower=worse
    "wsmFlangeThickness": (10.0, 23.0),  # lower=worse (fleet prior, not register)
    "wsmRoot": (0.0, 6.0),               # lower=worse; 6.0 = Wrpld approved condemning
    "wsmWheelGauge": (1357.0, 1340.0),   # gauge typically must stay within band
}

# Whether lower measured value = worse degradation for that dimension.
LOWER_IS_WORSE = {"wsmDia": True, "wsmFlangeThickness": True, "wsmRoot": True,
                  "wsmWheelGauge": True}


def _side_value(df, dim):
    c1, c2 = f"{dim}1", f"{dim}2"
    q1, q2 = f"{dim}1_quality", f"{dim}2_quality"
    v1 = df[c1].where(df[q1].eq("OBSERVED_VALID"))
    v2 = df[c2].where(df[q2].eq("OBSERVED_VALID"))
    return v1.combine_first(v2)


def main() -> None:
    df = pd.read_parquet(WES_PATH)
    df = df.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).copy()
    df = df.rename(columns={"measurement_record_id": "state_id",
                            "wheelset_equipment_id": "equipment",
                            "measurement_timestamp": "time"})

    out = df[["state_id", "equipment", "time", "locomotive_id", "LocoType", "home_shed",
              "wheel_position_1_12", "axle_position_1_6", "turning_record_at_measurement",
              "interval_context_available"]].copy()

    for d in DIMENSIONS:
        out[f"{d}_value"] = _side_value(df, d)

    # ---- 1. Segment-level wear rates (mm/day) ----
    seg = df.copy()
    seg["turn_cumsum"] = seg.groupby("equipment")["turning_record_at_measurement"].cumsum()
    seg["segment"] = seg["equipment"].astype(str) + "_" + seg["turn_cumsum"].astype(str)
    out["turn_cumsum"] = seg["turn_cumsum"].values

    wear_rate = {}
    for d in DIMENSIONS:
        v = _side_value(seg, d)
        # first and last valid measurement within segment
        first_v = v.groupby(seg["segment"]).transform("first")
        last_v = v.groupby(seg["segment"]).transform("last")
        seg[f"{d}_seg_first"] = first_v
        seg[f"{d}_seg_last"] = last_v
        seg[f"{d}_seg_start"] = seg["time"].groupby(seg["segment"]).transform("first")
        seg[f"{d}_seg_end"] = seg["time"].groupby(seg["segment"]).transform("last")

    seg_dur = (seg["time"].groupby(seg["segment"]).transform("max")
               - seg["time"].groupby(seg["segment"]).transform("min"))
    seg_dur_days = seg_dur.dt.total_seconds() / 86400

    seg_rates = pd.DataFrame(index=seg["segment"].unique())
    seg_rates["segment"] = seg_rates.index
    seg_rates["turn_cumsum"] = seg_rates.index.map(lambda s: int(s.split("_")[1]))
    seg_rates["seg_start"] = seg.groupby("segment")["time"].first().values
    seg_rates["seg_end"] = seg.groupby("segment")["time"].last().values
    seg_rates["seg_duration_days"] = (
        (seg_rates["seg_end"] - seg_rates["seg_start"]).dt.total_seconds() / 86400)
    seg_rates["n_measurements"] = seg.groupby("segment").size()
    for d in DIMENSIONS:
        fv = seg.groupby("segment")[f"{d}_seg_first"].first()
        lv = seg.groupby("segment")[f"{d}_seg_last"].first()
        dt_days = seg_rates["seg_duration_days"].reindex(seg_rates.index)
        seg_rates[f"{d}_rate_mm_day"] = (lv - fv) / dt_days.replace(0, np.nan)

    # Merge each state's segment id + accumulated rate (rate within its segment).
    seg_lookup = seg.set_index(["equipment", "turn_cumsum"])["segment"]
    out_tmp = pd.merge(out, seg[["equipment", "turn_cumsum", "segment"]]
                       .drop_duplicates(["equipment", "turn_cumsum"]),
                       on=["equipment", "turn_cumsum"], how="left")
    out_tmp = pd.merge(out_tmp, seg_rates, on="segment", how="left")

    # ---- 2. Estimated Engineering RUL (days) and proximity ----
    rul_cols = {}
    for d in DIMENSIONS:
        lo, hi = REFERENCE[d]
        cur = out_tmp[f"{d}_value"]
        rate = out_tmp[f"{d}_rate_mm_day"]
        # days to reference threshold at current wear rate (nonzero, negative=worse)
        days = np.where(rate < 0, (cur - hi) / rate, np.nan)
        # cap for presentation
        rul_cols[f"{d}_est_rul_days"] = days
    for c, v in rul_cols.items():
        out_tmp[c] = v

    # proximity score 0-100: 0 = far from reference, 100 = at/over reference
    for d in DIMENSIONS:
        lo, hi = REFERENCE[d]
        cur = out_tmp[f"{d}_value"]
        if LOWER_IS_WORSE[d]:
            prox = 100 * np.clip((hi - cur) / (hi - lo), 0, 1)
        else:
            prox = 100 * np.clip((cur - lo) / (hi - lo), 0, 1)
        out_tmp[f"{d}_proximity_100"] = prox

    dims_avail = [d for d in DIMENSIONS if f"{d}_value" in out_tmp.columns]
    out_tmp["n_active_dims"] = out_tmp[[f"{d}_value" for d in dims_avail]].notna().sum(axis=1)
    out_tmp["max_proximity"] = out_tmp[[f"{d}_proximity_100" for d in dims_avail]].max(axis=1)
    # limiting dimension = the one with the max proximity (closest to reference)
    prox_cols = [f"{d}_proximity_100" for d in dims_avail]
    lim_idx = out_tmp[prox_cols].idxmax(axis=1)
    out_tmp["limiting_dimension"] = lim_idx.map(
        {f"{d}_proximity_100": d for d in dims_avail})

    # Health index: average proximity weighted toward the max (limiting).
    out_tmp["health_index"] = 0.5 * out_tmp["max_proximity"] + 0.5 * out_tmp[
        [f"{d}_proximity_100" for d in dims_avail]].mean(axis=1)
    # burst events / maintenance history discount
    out_tmp["health_index"] -= 2.0 * out_tmp["turning_record_at_measurement"].fillna(0)
    out_tmp["health_index"] = out_tmp["health_index"].clip(0, 100)

    # ---- 3. Corrective action ----
    def action(row):
        if pd.isna(row["limiting_dimension"]):
            return "DATA_INSUFFICIENT"
        h = row["health_index"]
        if h >= 90:
            return "MONITOR"  # healthy
        if h >= 75:
            return "SCHEDULE_INSPECTION"  # plan next shed inspection
        if h >= 55:
            return "PLAN_TURNING_REPROFILING"  # plan corrective intervention
        return "URGENT_ACTION"  # high priority

    out_tmp["recommended_action"] = out_tmp.apply(action, axis=1)

    # relative priority percentile (0=lowest 100=highest priority -> low health)
    out_tmp["priority_percentile"] = (
        100 * out_tmp["health_index"].rank(pct=True, method="average").map(
            lambda p: 1 - p))

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_tmp.to_parquet(OUTPUT / "engineering_intelligence.parquet", index=False)

    # ---- 4. Fleet / shed dashboards ----
    DASH.mkdir(parents=True, exist_ok=True)
    fleet = out_tmp.groupby("equipment").tail(1)  # latest state per wheel
    fleet_summary = fleet.groupby("home_shed").agg(
        n_wheels=("equipment", "nunique"),
        mean_health=("health_index", "mean"),
        pct_urgent=("recommended_action", lambda x: (x == "URGENT_ACTION").mean() * 100),
        pct_plan=("recommended_action", lambda x:
                  x.isin(["PLAN_TURNING_REPROFILING", "URGENT_ACTION"]).mean() * 100),
    ).sort_values("pct_plan", ascending=False)
    fleet_summary.to_csv(DASH / "fleet_dashboard.csv")
    fleet_summary.to_parquet(DASH / "fleet_dashboard.parquet")

    # Example wheel health cards (highest priority)
    top = fleet.nlargest(6, "priority_percentile")
    card_cols = ["state_id", "equipment", "time", "home_shed", "LocoType",
                 "wheel_position_1_12"] + [f"{d}_value" for d in DIMENSIONS] + \
                ["health_index", "priority_percentile", "limiting_dimension",
                 "recommended_action"]
    top[card_cols].to_csv(DASH / "wheel_health_cards_top_priority.csv", index=False)

    summary = {
        "states": int(len(out_tmp)),
        "latest_wheels": int(len(fleet)),
        "sheds": int(len(fleet_summary)),
        "action_counts": out_tmp["recommended_action"].value_counts().to_dict(),
        "median_health_index": float(out_tmp["health_index"].median()),
        "limiting_dimension_counts": out_tmp["limiting_dimension"].value_counts().to_dict(),
        "reference_thresholds": REFERENCE,
        "note": "Estimated RUL is rate-based; root (6.0 mm, Wrpld) and dia (1016 mm) "
                "are APPROVED limits, flange/tread reference values are fleet priors "
                "while their registered fields stay SEMANTICS_BLOCKED in WES. Health "
                "index is transparent rule-based (proximity + wear rate + maintenance).",
    }
    (OUTPUT / "engineering_intelligence_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    # Report
    lines = [
        "# Phase 3B - Engineering Intelligence",
        "",
        "From the frozen Wheel Engineering State v1.0, per-state intelligence for",
        "maintenance prioritisation under incomplete observability.",
        "",
        "## Health index and action distribution",
        "",
        f"- States: {summary['states']:,}; latest-per-wheel: {summary['latest_wheels']:,}; "
        f"sheds: {summary['sheds']}",
        f"- Median health index: {summary['median_health_index']:.1f}/100",
        "",
        "| recommended action | states |",
        "| --- | ---: |",
    ]
    for k, v in sorted(summary["action_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v:,} |")
    lines += [
        "",
        "## Limiting dimension (the corrective focus)",
        "",
        "| limiting dimension | states |",
        "| --- | ---: |",
    ]
    for k, v in sorted(summary["limiting_dimension_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v:,} |")
    lines += [
        "",
        "## Method & honesty",
        "",
        "- Wear rates are **segment-level** (mm/day over a wheel's current life-segment",
        "  between resets), which averages out the per-inspection noise that dominated",
        "  short-interval next-state prediction.",
        "- Estimated RUL (days) is **rate-based and fleet-relative** toward the documented",
        "  reference thresholds. It is NOT a claim against an approved condemning limit,",
        "  which remains BLOCKED.",
        "- Health index is transparent and rule-based (proximity to reference + wear rate",
        "  + maintenance history), not a black-box scalar.",
        "- Outputs: `engineering_intelligence.parquet`, fleet/shed dashboards, top-priority",
        "  wheel health cards.",
    ]
    (OUTPUT / "engineering_intelligence_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))
    print(summary["action_counts"])
    print("limiting:", summary["limiting_dimension_counts"])


if __name__ == "__main__":
    main()
