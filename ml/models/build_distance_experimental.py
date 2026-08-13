"""Build the experimental RTIS interval-distance features for the V2 ablation.

EXPERIMENTAL — not a Feature Store release.  The released distance feature stays
BLOCKED (docs/rtis_distance_semantics.md, RTIS_DISTANCE_FEATURE_STATUS=BLOCKED)
until the RTIS source owner approves the grain/aggregation rule.

Rule used here (owner-approval candidate, from distance_semantics_findings.md):
  - Grain: locomotive + report date + division + distance (RlkdId is a re-ingest
    artifact, not a business key).
  - Dedupe: keep the FIRST row per exact key (loco, date, division, distance).
  - interval_distance_km_experimental = sum of deduped reported_distance_km over
    reports in the interval, boundary (start, end] — identical to the exposure
    layer's rtis_* metadata lookup.
  - rtis_distance_coverage_days = number of distinct report DAYS with a deduped
    report inside the interval.  Missing report != 0 km; the coverage denominator
    lets downstream code treat a sparse interval as unknown, not zero.

Outputs a CSV/parquet of the two experimental columns keyed by
operational_exposure_id for the V2 ablation runner.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SILVER_RTIS = PROJECT_ROOT / "data" / "silver" / "rtis_mileage.parquet"
DATASET_V1_2 = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
OUTPUT = PROJECT_ROOT / "model_datasets" / "v1.2" / "distance_experimental.parquet"


def _normalise_loco_number(values: pd.Series) -> pd.Series:
    raw = values.astype("string").str.strip().str.upper().str.replace(r"\s+", "", regex=True)
    numeric = pd.to_numeric(raw, errors="coerce")
    return numeric.astype("Int64").astype("string").where(numeric.notna(), raw)


def build_interval_distance(rtis: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    """Return interval_distance_km_experimental + rtis_distance_coverage_days.

    Mirrors silver_gold/operational_exposure._rtis_metadata's searchsorted
    boundary semantics exactly: interval_start exclusive, interval_end inclusive.
    """
    events = rtis.copy()
    events["loco_key"] = _normalise_loco_number(events["loco_number"])
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"], errors="coerce")
    events = events.dropna(subset=["loco_key", "event_timestamp"])

    key = ["loco_key", "event_timestamp", "RlkdDivision", "reported_distance_km"]
    events = events.drop_duplicates(subset=key, keep="first")

    distance = np.full(len(intervals), np.nan)
    coverage_days = np.zeros(len(intervals), dtype=np.int64)

    events_index = {
        loco: group.sort_values("event_timestamp")
        for loco, group in events.groupby("loco_key", sort=False)
    }
    indexed = intervals.reset_index(drop=False).rename(columns={"index": "interval_row"})
    indexed["loco_key"] = _normalise_loco_number(indexed["loco_number"])
    for loco, group in indexed.groupby("loco_key", sort=False):
        subset = events_index.get(loco)
        if subset is None or subset.empty:
            continue
        times = subset["event_timestamp"].to_numpy(dtype="datetime64[ns]")
        values = subset["reported_distance_km"].to_numpy(dtype=np.float64)
        day_values = times.astype("datetime64[D]")
        unique_days = np.unique(day_values)
        rows = group["interval_row"].to_numpy()
        starts = group["interval_start_timestamp"].to_numpy(dtype="datetime64[ns]")
        ends = group["interval_end_timestamp"].to_numpy(dtype="datetime64[ns]")
        left = np.searchsorted(times, starts, side="right")
        right = np.searchsorted(times, ends, side="right")
        present = right > left
        present_idx = np.nonzero(present)[0]
        end_days = ends.astype("datetime64[D]")
        start_days = starts.astype("datetime64[D]")
        for k, row in enumerate(rows[present_idx]):
            i = present_idx[k]
            l, r = left[i], right[i]
            distance[row] = float(np.sum(values[l:r]))
            coverage_days[row] = (
                np.searchsorted(unique_days, end_days[i], side="right")
                - np.searchsorted(unique_days, start_days[i], side="right")
            )
    result = pd.DataFrame(
        {
            "interval_distance_km_experimental": distance,
            "rtis_distance_coverage_days": coverage_days,
        },
        index=intervals.index,
    )
    result["rtis_distance_coverage_pct"] = np.where(
        intervals["interval_days"].gt(0),
        (result["rtis_distance_coverage_days"] / intervals["interval_days"]) * 100,
        np.nan,
    )
    return result


def main() -> None:
    rtis = pd.read_parquet(SILVER_RTIS)
    dataset = pd.read_parquet(DATASET_V1_2)

    meta_cols = [
        "operational_exposure_id",
        "locomotive_number",
        "interval_start_timestamp",
        "interval_end_timestamp",
        "interval_days",
    ]
    missing = [c for c in meta_cols if c not in dataset.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    intervals = dataset[meta_cols].copy()
    intervals = intervals.rename(columns={"locomotive_number": "loco_number"})
    result = build_interval_distance(rtis, intervals)
    result["operational_exposure_id"] = dataset["operational_exposure_id"].values
    out_cols = [
        "operational_exposure_id",
        "interval_distance_km_experimental",
        "rtis_distance_coverage_days",
        "rtis_distance_coverage_pct",
    ]
    result[out_cols].to_parquet(OUTPUT, index=False)

    nonzero = result["interval_distance_km_experimental"].notna().sum()
    summary = {
        "intervals": len(result),
        "intervals_with_distance": int(nonzero),
        "intervals_without_reports": int((result["rtis_distance_coverage_days"] == 0).sum()),
        "median_distance_km_when_reported": float(result.loc[result["interval_distance_km_experimental"].notna(), "interval_distance_km_experimental"].median()),
        "p99_distance_km_when_reported": float(result.loc[result["interval_distance_km_experimental"].notna(), "interval_distance_km_experimental"].quantile(0.99)),
        "median_coverage_pct": float(result["rtis_distance_coverage_pct"].median()),
        "output": str(OUTPUT),
    }
    print(json.dumps(summary, indent=2))
    print(f"\nwrote -> {OUTPUT}")


if __name__ == "__main__":
    main()
