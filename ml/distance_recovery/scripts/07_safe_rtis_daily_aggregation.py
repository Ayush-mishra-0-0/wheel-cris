"""Safe multi-division RTIS daily aggregation with double-data/outlier rejection.

Tests the hypothesis: multi-division km CAN be summed safely IF re-ingested
duplicates are removed AND physically-implausible daily totals are treated as
double-data and rejected.

Rule implemented:
  1. Exact business-key dedupe (loco, date, division, distance) keep latest load
     (removes the documented re-ingested reports: 153,221 excess rows).
  2. Sum the remaining division rows per loco-day  -> candidate daily km.
  3. Flag double-data signature: a (loco, date, division) with MULTIPLE distinct
     distance values on the same day (reloads with changed values).
  4. Flag outliers: daily total above an absolute physical cap OR > k x the
     loco's own median daily total.
  5. Reject flagged loco-days from the safe distance table.

This is an EXPERIMENTAL candidate aggregation. It builds evidence for upgrading
`RTIS_DISTANCE_FEATURE_STATUS` from BLOCKED, but does not replace the source
owner's sign-off (docs/rtis_distance_semantics.md, release check #2).

Outputs:
  data/processed/rtis_daily_safe.parquet   loco, day, rtis_km_safe, n_divisions,
                                           n_distinct_distances, outlier_flag,
                                           double_data_flag
  reports/rtis_safe_aggregation_report.md

Usage:
  python scripts/07_safe_rtis_daily_aggregation.py [--rtis-mileage PATH]
      [--cap-km 4000] [--rel-mult 5.0]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "reports"
PROC = PROJECT_ROOT / "data" / "processed"
DEFAULT_RTIS = PROJECT_ROOT.parent / "data" / "silver" / "rtis_mileage.parquet"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtis-mileage", type=str, default=str(DEFAULT_RTIS))
    ap.add_argument("--cap-km", type=float, default=4000.0,
                    help="absolute physical cap for a plausible loco-day (km)")
    ap.add_argument("--rel-mult", type=float, default=5.0,
                    help="daily total above this multiple of the loco's own median is an outlier")
    ap.add_argument("--div-cap-km", type=float, default=1200.0,
                    help="single division-day distance above this is multi-day/double counting")
    args = ap.parse_args()

    df = pd.read_parquet(args.rtis_mileage)
    df["day"] = pd.to_datetime(df["event_timestamp"]).dt.normalize()
    n_raw = len(df)

    # 1. exact business-key dedupe (re-ingested reports), keep latest load
    df = df.sort_values("RlkdSlamEntryDate").drop_duplicates(
        subset=["loco_number", "day", "RlkdDivision", "RlkdTotalDistance"], keep="last")
    n_dedup = len(df)

    # 2. per loco-day division statistics
    div = df.groupby(["loco_number", "day"]).agg(
        n_divisions=("RlkdDivision", "nunique"),
        n_distinct_distances=("RlkdTotalDistance", "nunique"),
    ).reset_index()
    daily = df.groupby(["loco_number", "day"])["RlkdTotalDistance"].sum().reset_index()
    daily.columns = ["loco", "day", "rtis_km_candidate"]
    daily = daily.merge(div, left_on=["loco", "day"], right_on=["loco_number", "day"], how="left")
    daily = daily.drop(columns=["loco_number"])

    # a division-day reported more than one distinct distance = reload/double data
    per = df.groupby(["loco_number", "day", "RlkdDivision"])["RlkdTotalDistance"].nunique()
    multi_val_divs = (per > 1).groupby(level=[0, 1]).sum()
    daily["double_data_divs"] = daily.set_index(["loco", "day"]).index.map(multi_val_divs.get).fillna(0)

    # 4. outlier flags
    med = daily.groupby("loco")["rtis_km_candidate"].median()
    daily["loco_median_km"] = daily["loco"].map(med)
    daily["above_cap"] = daily["rtis_km_candidate"] > args.cap_km
    daily["above_rel"] = daily["rtis_km_candidate"] > args.rel_mult * daily["loco_median_km"]
    # a single division-day carrying more than a plausible one-day division run
    # (Indian divisions are <~800 km) is multi-day/double counting
    div_max = df.groupby(["loco_number", "day"])["RlkdTotalDistance"].max()
    daily["max_division_km"] = daily.set_index(["loco", "day"]).index.map(div_max.get).fillna(0)
    daily["div_over_cap"] = daily["max_division_km"] > args.div_cap_km
    daily["outlier_flag"] = daily["above_cap"] | daily["above_rel"] | daily["div_over_cap"]
    daily["double_data_flag"] = (daily["double_data_divs"] > 0) & daily["outlier_flag"]

    # 5. safe table: reject outliers
    safe = daily[~daily["outlier_flag"]].copy()
    safe["rtis_km_safe"] = safe["rtis_km_candidate"].round(2)
    safe = safe[["loco", "day", "rtis_km_safe", "n_divisions", "n_distinct_distances",
                 "double_data_divs", "max_division_km", "outlier_flag", "double_data_flag"]]
    PROC.mkdir(parents=True, exist_ok=True)
    out = PROC / "rtis_daily_safe.parquet"
    safe.to_parquet(out, index=False)
    # full candidate frame (incl. outliers) so 08 can adjudicate with FOIS evidence
    daily[["loco", "day", "rtis_km_candidate", "n_divisions", "max_division_km",
           "outlier_flag", "double_data_flag"]].to_parquet(PROC / "rtis_daily_candidate.parquet", index=False)

    outl = daily[daily["outlier_flag"]]
    dd = outl[outl["double_data_flag"]]
    sig = ["above_cap", "above_rel", "div_over_cap"]
    rule_breakdown = " · ".join(f"{c}: {outl[c].sum():,}" for c in sig)
    lines = [
        "# Safe RTIS daily aggregation (multi-division km + double-data rejection)",
        "",
        f"Input: `{args.rtis_mileage}` · rows {n_raw:,} → after exact business-key dedupe {n_dedup:,} "
        f"(removed {n_raw - n_dedup:,} re-ingested duplicates)",
        f"Loco-days: {len(daily):,} · multi-division loco-days: {(daily['n_divisions'] > 1).sum():,}",
        "",
        "## Candidate daily sum BEFORE rejection",
        "",
        f"- max: {daily['rtis_km_candidate'].max():,.1f} km/day",
        f"- p99: {daily['rtis_km_candidate'].quantile(0.99):,.1f} km/day",
        f"- median: {daily['rtis_km_candidate'].median():,.1f} km/day",
        "",
        "## Outlier / double-data rejection",
        "",
        f"- flagged outliers: {len(outl):,} ({len(outl)/len(daily)*100:.3f}%)",
        f"- rule hits: {rule_breakdown}",
        f"- of those with a division carrying multiple distinct distances (within-division double report): {len(dd):,}",
        f"- max outlier: {outl['rtis_km_candidate'].max():,.1f} km/day",
        f"- max single division-day within outliers: {outl['max_division_km'].max():,.1f} km",
        "",
        "## Safe daily table (outliers rejected)",
        "",
        f"- retained loco-days: {len(safe):,} ({len(safe)/len(daily)*100:.3f}%)",
        f"- retained max: {safe['rtis_km_safe'].max():,.1f} km/day · p99: {safe['rtis_km_safe'].quantile(0.99):,.1f} km/day",
        f"- retained max single division-day: {safe['max_division_km'].max():,.1f} km",
        f"- multi-division retained: {(safe['n_divisions'] > 1).mean()*100:.1f}%",
        "",
        "## Interpretation (honest)",
        "",
        "- 'Outlier = double data' is only PARTIALLY supported. Within-division duplicate",
        "  reports (same division, two different distances) explain just a few outliers.",
        "- The dominant outlier signature is ONE division-day carrying an implausibly",
        "  large distance (e.g., DLI 2,285 km in a day — no Indian division is that long),",
        "  which is multi-day/cumulative mislabelling, i.e. a different form of double count.",
        "- The combined rule (dedupe + daily cap + per-division cap + relative cap) keeps "
        f"{len(safe):,} loco-days (99.9%) with a physically plausible daily total.",
        "- Still PENDING RTIS owner sign-off: this script only builds the evidence "
        "(docs/rtis_distance_semantics.md release check #2).",
        "",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    rep = REPORTS / "rtis_safe_aggregation_report.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {rep}")
    print(f"  loco-days {len(daily):,} · dedup removed {n_raw - n_dedup:,} · outliers {len(outl):,} "
          f"({len(outl)/len(daily)*100:.2f}%) · safe retained {len(safe):,}")
    print(f"  outliers with double-data signature: {len(dd)} ({len(dd)/max(len(outl),1)*100:.0f}%)")


if __name__ == "__main__":
    main()
