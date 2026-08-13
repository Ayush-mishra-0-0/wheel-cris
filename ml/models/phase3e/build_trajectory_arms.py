"""Phase 3E - point-in-time trajectory / history features (v3e).

Adds an explicit information ladder to the Phase 3D horizon-window substrate.
For every measurement-origin row we add, using ONLY information available at or
before prediction time t, three deliberately-separate history families:

  S_t        current state (already present in v3d)
  S_{t-k:t}  TRAJECTORY: trailing changes & rates over 30/90/180 days,
             inspection intensity, lifecycle age, days since last inspection
  E_{t-k:t}  EXPOSURE history: trailing km (sum of approved forward-interval
             distances for inspections inside the window) + coverage flags
  O_t        operational / loco context (carried from v3d)

Rules (non-negotiable):
  * Windows use measurements with timestamp strictly < t. The row's own
    measurement never enters its own history window.
  * History is censored at the LAST CONFIRMED+LIKELY replacement before t: the
    lower bound of any window is max(t - W, segment_start). The trajectory
    therefore always belongs to the CURRENT physical wheel only.
  * No history in a window => NaN value plus an explicit `*_available` flag.
    No imputation anywhere.

Trajectory stream is built from WES v1.0 (full per-measurement state layer) so
windows see every inspection, then joined onto v3d by measurement_record_id.
Row identity: v3d within-lifecycle row set, same order.

Output   : model_datasets/v3e/forecast_information_ladder.parquet
Manifest : model_datasets/v3e/forecast_information_ladder_manifest_v1.0.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3c"))

from degradation_eval import ROW_ID_COL, DIMENSIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3D = ROOT / "model_datasets" / "v3d" / "forecast_horizon_benchmark_pairs.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
EXPOSURE = ROOT / "model_datasets" / "v2" / "exposure_features_v2.parquet"
LEDGER = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0" / "engineering_event_ledger.parquet"
OUTPUT = ROOT / "model_datasets" / "v3e"

TRAJ_WINDOWS = [30, 90, 180]
DAY = np.timedelta64(1, "D")

# Physical single-gap bound (mm): any single inspection-to-inspection |Δ| above
# this marks the window non-contiguous (an undocumented replacement/jump). Far
# beyond plausible peer-interval wear; framed as a guard, not a claim.
GAP_BOUND_MM = {"wsmDia": 30.0, "wsmFlangeThickness": 5.0, "wsmRoot": 5.0,
                "wsmWheelGauge": 10.0}
MIN_WINDOW_KM = 50.0   # km floor for per-1000km rates (avoid div-by-tiny)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _side_state(wes: pd.DataFrame, d: str) -> np.ndarray:
    s1, s2 = f"{d}1", f"{d}2"
    v1 = wes[f"{s1}_quality"].eq("OBSERVED_VALID").to_numpy()
    v2 = wes[f"{s2}_quality"].eq("OBSERVED_VALID").to_numpy()
    a = wes[s1].to_numpy(dtype=float)
    b = wes[s2].to_numpy(dtype=float)
    return np.where(v1 & v2, (a + b) / 2.0, np.where(v1, a, np.where(v2, b, np.nan)))


def replacement_times() -> dict[int, np.ndarray]:
    led = pd.read_parquet(LEDGER)
    rep = led[(led["event_type"] == "replacement")
              & (led["confidence"].isin(["CONFIRMED", "LIKELY"]))][
        ["wheelset_equipment_id", "event_date"]].dropna()
    if rep.empty:
        return {}
    rep["w"] = rep["wheelset_equipment_id"].astype("int64")
    ev = pd.to_datetime(rep["event_date"]).to_numpy(dtype="datetime64[us]")
    wids = rep["w"].to_numpy()
    return {k: np.sort(ev[wids == k]) for k in np.unique(wids)}


def _trajectory_stream(wes: pd.DataFrame,
                       rep_map: dict[int, np.ndarray]) -> pd.DataFrame:
    """Per-measurement trailing features; one row per WES measurement in the
    SAME order as `wes`. Returns a frame keyed by ROW_ID_COL."""
    rid = wes[ROW_ID_COL].to_numpy()
    wid = wes["wheelset_equipment_id"].astype("int64").to_numpy()
    tms = pd.to_datetime(wes["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    fkm = wes["interval_distance_km"].to_numpy(dtype=float)
    states = {d: _side_state(wes, d) for d in DIMENSIONS}

    accum = {ROW_ID_COL: [], "days_since_last_inspection": [],
             "days_since_segment_start": []}
    for Wd in TRAJ_WINDOWS:
        accum[f"inspection_count_{Wd}d"] = []
    for Wd in TRAJ_WINDOWS:
        accum[f"km_last_{Wd}d"] = []
        accum[f"km_{Wd}d_available"] = []
    for Wd in TRAJ_WINDOWS:
        for d in DIMENSIONS:
            accum[f"{d}_change_last_{Wd}d"] = []
            accum[f"{d}_rate_per_day_{Wd}d"] = []
            accum[f"{d}_rate_per_1000km_{Wd}d"] = []

    for w in np.unique(wid):
        sel = np.where(wid == w)[0]
        ts = tms[sel]
        kmv = fkm[sel]
        n = len(sel)
        repl = rep_map.get(int(w), np.array([], dtype="datetime64[us]"))

        lr = np.searchsorted(repl, ts, side="right") - 1
        seg_start = np.full(n, np.datetime64("NaT"), dtype="datetime64[us]")
        pos = lr >= 0
        if len(repl):
            seg_start[pos] = repl[np.clip(lr, 0, None)][pos]

        ds = np.full(n, np.nan)
        if n > 1:
            ds[1:] = (ts[1:] - ts[:-1]) / DAY
        seg_days = np.full(n, np.nan)
        seg_days[pos] = (ts[pos] - seg_start[pos]) / DAY

        avail = (~np.isnan(fkm[sel])).astype(float)
        km_cum = np.concatenate([[0.0], np.nan_to_num(fkm[sel]).cumsum()])
        av_cum = np.concatenate([[0.0], np.cumsum(avail)])
        ri = np.arange(n)

        for Wd in TRAJ_WINDOWS:
            low = ts - np.timedelta64(Wd, "D")
            eff = low.copy()
            eff[pos] = np.maximum(low[pos], seg_start[pos])
            lo_idx = np.searchsorted(ts, eff, side="left").astype(int)
            has_prior = lo_idx < ri
            lo_safe = np.where(has_prior, lo_idx, np.maximum(ri - 1, 0))

            count = np.where(has_prior, ri - lo_idx, 0)
            kmW = np.where(has_prior, km_cum[ri] - km_cum[lo_safe], np.nan)
            okW = (av_cum[ri] - av_cum[lo_safe]) > 0
            accum[f"inspection_count_{Wd}d"].append(count)
            accum[f"km_last_{Wd}d"].append(kmW)
            accum[f"km_{Wd}d_available"].append(okW)

            for d in DIMENSIONS:
                st = states[d][sel]
                bound = GAP_BOUND_MM[d]
                # single-gap step within the referenced window; any |step| >
                # bound => non-contiguous (jump), null all trajectory values.
                # steps over delta(iloc diff); compute per-window max step via
                # a rolling max of |consecutive diff| over [lo_safe, i].
                step = np.full(n, np.nan)
                if n > 1:
                    step[1:] = np.abs(np.diff(st))
                # cumulative max step up to each prior position
                cummax_step = np.maximum.accumulate(np.nan_to_num(step, nan=0.0))
                # window max step = max over (lo_safe, i]; use cummax at i-1
                wmax = np.where(has_prior & (ri >= 1), cummax_step[np.maximum(ri - 1, 0)], 0.0)
                contiguous = (~has_prior) | (wmax <= bound)

                ref = st[lo_safe]
                chg = np.where(has_prior, st - ref, np.nan)
                span = np.where(has_prior, (ts - ts[lo_safe]) / DAY, np.nan)
                rd = np.where(has_prior & (span > 1e-9), chg / np.maximum(span, 1e-9), np.nan)
                km_ok = okW & (kmW >= MIN_WINDOW_KM)
                rk = np.where(has_prior & km_ok, chg / np.maximum(kmW / 1000.0, 1e-9), np.nan)
                # null out non-contiguous windows (their change spans another wheel)
                chg = np.where(contiguous, chg, np.nan)
                rd = np.where(contiguous, rd, np.nan)
                rk = np.where(contiguous, rk, np.nan)
                accum[f"{d}_change_last_{Wd}d"].append(chg)
                accum[f"{d}_rate_per_day_{Wd}d"].append(rd)
                accum[f"{d}_rate_per_1000km_{Wd}d"].append(rk)

        accum[ROW_ID_COL].append(rid[sel])
        accum["days_since_last_inspection"].append(ds)
        accum["days_since_segment_start"].append(seg_days)

    flat = {k: np.concatenate(v) for k, v in accum.items()}
    df = pd.DataFrame(flat)
    return df.set_index(ROW_ID_COL).loc[rid].reset_index()


def main() -> None:
    wes = pd.read_parquet(WES)
    exp = pd.read_parquet(EXPOSURE,
                          columns=["operational_exposure_id", "interval_distance_km"])
    wes = wes.merge(exp, on="operational_exposure_id", how="left")
    rep_map = replacement_times()
    traj = _trajectory_stream(wes, rep_map)

    v3d = pd.read_parquet(V3D)
    v3d = v3d.merge(traj, on=ROW_ID_COL, how="left")
    n_nan = int(v3d["days_since_last_inspection"].isna().sum())
    print(f"v3d rows {len(v3d)}; no-inspection-history rows: {n_nan}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "forecast_information_ladder.parquet"
    v3d.to_parquet(out_path, index=False)
    manifest = {
        "dataset": "forecast_information_ladder",
        "version": "1.0.0",
        "inputs": {"v3d": str(V3D.relative_to(ROOT)),
                   "wes": str(WES.relative_to(ROOT)),
                   "exposure": str(EXPOSURE.relative_to(ROOT)),
                   "ledger": str(LEDGER.relative_to(ROOT))},
        "output_sha256": _sha256(out_path),
        "rows": int(len(v3d)),
        "trajectory_windows": TRAJ_WINDOWS,
        "point_in_time": "history strictly < t; segment censored at last replacement",
        "missingness": "NaN + availability flags; no imputation",
    }
    (OUTPUT / "forecast_information_ladder_manifest_v1.0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()