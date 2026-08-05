"""Workstream 1 — Operational Exposure features, Phase 2 (V2.0).

EXTENDS the released v1.2 chain: this builder consumes the v1.2 dataset
(immutable) and the owner-APPROVED RTIS safe daily ledger
(distance_recovery/data/processed/rtis_daily_safe.parquet,
"sum the deduped per-loco per-day division distances", signed off 2026-08-05)
and emits a per-interval exposure table keyed by operational_exposure_id.

Feature families (WS1 Exposure layer):
  - interval_distance_km                approved daily-ledger sum over the interval, (start, end]
  - rtis_distance_coverage_days/pct_in_interval   reporting-day coverage of that sum
  - distance_per_day_km                 interval_distance_km / interval_days
  - distance_since_last_inspection_km   identical value; semantic framing only (the interval
                                        boundary IS the time since the last wheel inspection)
  - running_days / running_days_pct     days in interval with approved distance > 0
  - running_hours_proxy                 FOIS-reported active movement time (bounded gaps);
                                        LOW COVERAGE (FOIS window 2025-10 -> 2026-06)
  - maintenance_density_per_day         maintenance_jobcard_creation_count / interval_days
  - maintenance_density_per_1000km      maintenance_jobcard_creation_count / (km / 1000)
  - distance_since_turning_km           cumulative approved km since last wsmturning=1 date
                                        (same wheelset equipment); NULL if no turning in history

Weather (WS1): NOT materialised. No provider/archive exists; weather_exposure_index stays
PENDING in configs/engineering_feature_specification_v1.json and this table carries no
all-null column (blocked-value rule: a PENDING feature is not materialised as estimates).

Point-in-time safe by construction: every column uses only daily reports with day <=
interval_end_timestamp.

GOVERNANCE: interval_distance_km_experimental (models/build_distance_experimental.py) is
left UNRENAMED and untouched; this table adds the approved column under its canonical name.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from silver_gold.transform import _sha256  # noqa: E402

V1_2_DATASET = PROJECT_ROOT / "model_datasets" / "v1.2" / "model_dataset_v1.2.parquet"
RTIS_DAILY_SAFE = PROJECT_ROOT / "distance_recovery" / "data" / "processed" / "rtis_daily_safe.parquet"
FOIS_TRANSITIONS = PROJECT_ROOT / "distance_recovery" / "data" / "processed" / "fois_transition_distances.parquet"
WHEEL_MEASUREMENTS = PROJECT_ROOT / "data" / "silver" / "wheel_measurements.parquet"
OUT_DIR = PROJECT_ROOT / "model_datasets" / "v2"

EXPOSURE_VERSION = "v2.0"
MAX_RUNNING_GAP_HOURS = 6.0


def _norm_loco(values: pd.Series) -> pd.Series:
    raw = values.astype("string").str.strip().str.upper().str.replace(r"\s+", "", regex=True)
    numeric = pd.to_numeric(raw, errors="coerce")
    return numeric.astype("Int64").astype("string").where(numeric.notna(), raw)


def _ledger_cumsum(events: pd.DataFrame, loco_col: str, day_col: str,
                   val_col: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-loco day-array + cumulative-value-array, sorted by day."""
    events = events.sort_values([loco_col, day_col])
    events["_cum"] = events.groupby(loco_col, sort=False)[val_col].cumsum()
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for lk, g in events.groupby(loco_col, sort=False):
        out[lk] = (g[day_col].to_numpy(dtype="datetime64[D]"),
                   g["_cum"].to_numpy(dtype=np.float64))
    return out


def _as_day(value) -> np.datetime64:
    return np.datetime64(pd.Timestamp(value).normalize(), "D")


def _sum_between(days: np.ndarray, cum: np.ndarray, start_day, end_day) -> float:
    """Sum of values with day in (start_day, end_day] via cumulative arrays."""
    if days.size == 0:
        return 0.0
    hi = np.searchsorted(days, _as_day(end_day), side="right")
    lo = np.searchsorted(days, _as_day(start_day), side="right")
    if hi <= lo:
        return 0.0
    return float(cum[hi - 1] - (cum[lo - 1] if lo > 0 else 0.0))


def _value_at(days: np.ndarray, cum: np.ndarray, day) -> float:
    """Cumulative value at the last day <= `day` (0 if before all days)."""
    if days.size == 0:
        return 0.0
    i = np.searchsorted(days, _as_day(day), side="right")
    return float(cum[i - 1]) if i > 0 else 0.0


def _build_interval_exposure(intervals: pd.DataFrame,
                             daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.sort_values(["loco", "day"])
    daily["km_cum"] = daily.groupby("loco", sort=False)["rtis_km_safe"].cumsum()
    daily["day_has_km"] = (daily["rtis_km_safe"] > 0).astype(np.float64)
    daily["day_has_km_cum"] = daily.groupby("loco", sort=False)["day_has_km"].cumsum()

    led = {}
    for lk, g in daily.groupby("loco", sort=False):
        led[lk] = (
            g["day"].to_numpy(dtype="datetime64[D]"),
            g["km_cum"].to_numpy(dtype=np.float64),
            g["day_has_km_cum"].to_numpy(dtype=np.float64),
        )

    loco = _norm_loco(intervals["locomotive_number"]).to_numpy()
    starts = pd.to_datetime(intervals["interval_start_timestamp"]).dt.normalize().to_numpy(dtype="datetime64[D]")
    ends = pd.to_datetime(intervals["interval_end_timestamp"]).dt.normalize().to_numpy(dtype="datetime64[D]")

    n = len(intervals)
    interval_km = np.full(n, np.nan)
    cov_days = np.zeros(n, dtype=np.float64)
    run_days = np.zeros(n, dtype=np.float64)

    for i in range(n):
        d = led.get(loco[i])
        if d is None:
            continue
        days, km_cum, has_km_cum = d
        hi = np.searchsorted(days, ends[i], side="right")
        lo = np.searchsorted(days, starts[i], side="right")
        if hi > lo:
            lo_cum = km_cum[lo - 1] if lo > 0 else 0.0
            lo_has = has_km_cum[lo - 1] if lo > 0 else 0.0
            interval_km[i] = km_cum[hi - 1] - lo_cum
            cov_days[i] = float(hi - lo)
            run_days[i] = has_km_cum[hi - 1] - lo_has

    days_arr = intervals["interval_days"].to_numpy(dtype=np.float64)
    result = pd.DataFrame({"operational_exposure_id": intervals["operational_exposure_id"].to_numpy()})
    result["interval_distance_km"] = interval_km
    result["rtis_distance_coverage_days_in_interval"] = cov_days
    result["rtis_distance_coverage_pct_in_interval"] = np.where(
        days_arr > 0, (cov_days / days_arr) * 100.0, np.nan)
    result["distance_per_day_km"] = np.where(days_arr > 0, interval_km / days_arr, np.nan)
    result["distance_since_last_inspection_km"] = interval_km

    jc = intervals["maintenance_jobcard_creation_count"].to_numpy(dtype=np.float64)
    result["maintenance_density_per_day"] = np.where(days_arr > 0, jc / days_arr, np.nan)
    per_1000 = np.full(n, np.nan)
    valid_km = (interval_km >= 1.0) & np.isfinite(interval_km)  # <1 km: not attributable travel
    per_1000[valid_km] = jc[valid_km] / (interval_km[valid_km] / 1000.0)
    result["maintenance_density_per_1000km"] = per_1000

    result["running_days"] = run_days
    result["running_days_pct"] = np.where(days_arr > 0, (run_days / days_arr) * 100.0, np.nan)
    return result, led


def _build_running_hours(intervals: pd.DataFrame) -> np.ndarray:
    out = np.full(len(intervals), np.nan)
    if not FOIS_TRANSITIONS.exists():
        return out
    trans = pd.read_parquet(FOIS_TRANSITIONS, columns=["loco", "time_a", "time_b"])
    trans["loco"] = _norm_loco(trans["loco"])
    trans["time_a"] = pd.to_datetime(trans["time_a"], errors="coerce")
    trans["time_b"] = pd.to_datetime(trans["time_b"], errors="coerce")
    trans = trans.dropna(subset=["loco", "time_a", "time_b"])
    dur_h = (trans["time_b"] - trans["time_a"]).dt.total_seconds() / 3600.0
    trans["active_h"] = dur_h.where(dur_h.between(0.0, MAX_RUNNING_GAP_HOURS), 0.0)
    led = _ledger_cumsum(trans, "loco", "time_b", "active_h")

    loco = _norm_loco(intervals["locomotive_number"]).to_numpy()
    starts = pd.to_datetime(intervals["interval_start_timestamp"]).dt.normalize().to_numpy(dtype="datetime64[D]")
    ends = pd.to_datetime(intervals["interval_end_timestamp"]).dt.normalize().to_numpy(dtype="datetime64[D]")
    for i in range(n := len(intervals)):
        d = led.get(loco[i])
        if d is None:
            continue
        days, cum = d
        # transition is "in the interval" when time_b in (start, end]
        hi = np.searchsorted(days, ends[i], side="right")
        lo = np.searchsorted(days, starts[i], side="right")
        if hi > lo:
            out[i] = cum[hi - 1] - (cum[lo - 1] if lo > 0 else 0.0)
    return out


def _distance_since_turning(intervals: pd.DataFrame, led,
                            interval_km: np.ndarray) -> np.ndarray:
    """Cumulative approved km between the last wsmturning=1 date (per wheelset
    equipment) and interval end, evaluated on the loco daily ledger. NULL if the
    equipment has no turning in history or the loco has no daily coverage."""
    meas = pd.read_parquet(WHEEL_MEASUREMENTS, columns=["wsmEquipmentId", "wsmUpdatedOn", "wsmturning1"])
    meas["equip"] = pd.to_numeric(meas["wsmEquipmentId"], errors="coerce")
    meas["ts"] = pd.to_datetime(meas["wsmUpdatedOn"], errors="coerce")
    meas["turn"] = pd.to_numeric(meas["wsmturning1"], errors="coerce")
    meas = meas.dropna(subset=["equip", "ts"])
    turn_events = meas.loc[meas["turn"] == 1, ["equip", "ts"]].sort_values(["equip", "ts"])
    turn_dates = {
        equip: g["ts"].dt.normalize().to_numpy(dtype="datetime64[D]")
        for equip, g in turn_events.groupby("equip", sort=False)
    }

    loco = _norm_loco(intervals["locomotive_number"]).to_numpy()
    equips = pd.to_numeric(intervals["wheelset_equipment_id"], errors="coerce").to_numpy()
    ends = pd.to_datetime(intervals["interval_end_timestamp"]).dt.normalize().to_numpy(dtype="datetime64[D]")

    out = np.full(len(intervals), np.nan)
    for i in range(len(intervals)):
        d = led.get(loco[i])
        if d is None:
            continue
        tdates = turn_dates.get(equips[i])
        if tdates is None or tdates.size == 0:
            continue
        k = np.searchsorted(tdates, ends[i], side="right") - 1  # last turning <= interval end
        if k < 0:
            continue
        lt = tdates[k]
        days, km_cum, _ = d
        out[i] = _value_at(days, km_cum, ends[i]) - _value_at(days, km_cum, lt)
    return out


def build_exposure_features_v2(force: bool = False) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "exposure_features_v2.parquet"
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} exists; use --force to regenerate")

    intervals = pd.read_parquet(
        V1_2_DATASET,
        columns=["operational_exposure_id", "locomotive_number", "interval_start_timestamp",
                 "interval_end_timestamp", "interval_days", "maintenance_jobcard_creation_count",
                 "wheelset_equipment_id"],
    )
    daily = pd.read_parquet(RTIS_DAILY_SAFE, columns=["loco", "day", "rtis_km_safe"])
    daily["loco"] = _norm_loco(daily["loco"])
    daily["day"] = pd.to_datetime(daily["day"], errors="coerce").dt.normalize()
    daily = daily.dropna(subset=["loco", "day", "rtis_km_safe"])
    daily["rtis_km_safe"] = pd.to_numeric(daily["rtis_km_safe"], errors="coerce").fillna(0.0)

    result, led = _build_interval_exposure(intervals, daily)
    result["running_hours_proxy"] = _build_running_hours(intervals)
    result["distance_since_turning_km"] = _distance_since_turning(
        intervals, led, result["interval_distance_km"].to_numpy(dtype=np.float64))

    for col in result.columns:
        result[col] = result[col].replace([np.inf, -np.inf], np.nan)

    missing = {c: float(result[c].isna().mean()) for c in result.columns if c != "operational_exposure_id"}
    manifest = {
        "exposure_version": EXPOSURE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "grain": "inspection interval (one Gold-B consecutive measurement pair), keyed by operational_exposure_id",
        "point_in_time_rule": "daily reports with day <= interval_end only",
        "boundary_rule": "(interval_start, interval_end] at day granularity",
        "distance_rule": "owner-APPROVED (2026-08-05): deduped per-loco per-day SUM of division km, outliers rejected (07_safe_rtis_daily_aggregation.py)",
        "input_sha256": {
            "v1.2_dataset": _sha256(V1_2_DATASET),
            "rtis_daily_safe": _sha256(RTIS_DAILY_SAFE),
            "fois_transitions": _sha256(FOIS_TRANSITIONS) if FOIS_TRANSITIONS.exists() else None,
            "wheel_measurements": _sha256(WHEEL_MEASUREMENTS),
        },
        "rows": int(len(result)),
        "columns": [c for c in result.columns],
        "expected_missing_pct": {k: round(v * 100, 2) for k, v in missing.items()},
        "notes": [
            "weather_exposure_index NOT materialised (PENDING, no provider) - blocked-value rule",
            "distance_since_turning_km uses wheel_measurements wsmturning=1 events; NULL where no turning in history",
            "running_hours_proxy is FOIS-window limited (2025-10 -> 2026-06)",
        ],
    }
    result.to_parquet(out_path, index=False)
    (OUT_DIR / "exposure_features_manifest_v2.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"exposure features v2: {result.shape} -> {out_path.relative_to(PROJECT_ROOT)}")
    for col, pct in sorted(missing.items(), key=lambda kv: -kv[1]):
        print(f"  {col:44s} missing {pct*100:6.2f}%")
    return {"exposure_features": out_path,
            "manifest": OUT_DIR / "exposure_features_manifest_v2.json"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, path in build_exposure_features_v2(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
