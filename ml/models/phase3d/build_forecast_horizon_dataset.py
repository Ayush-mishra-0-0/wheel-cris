"""Phase 3D - build the horizon-windowed forecast substrate (v3d).

Anchors the frozen Phase 3C within-lifecycle pairs and assigns every row a
unique horizon band by nearest nominal horizon using the evaluation windows of
docs/phase3c_plan.md §10:

    30d  [20, 45]    60d [45, 80]    90d [70, 120]
    180d [140, 240]  365d [300, 450]

Rows whose interval_days falls outside every window are banded `other`; they are
training-only and never forecast-evaluated at a nominal horizon.

Also materialises `replacement_before_{H}d` per horizon from the governed Event
Ledger (CONFIRMED + LIKELY replacement strictly inside
(measurement_time, measurement_time + H]) as an explicit censoring flag. No rows
are dropped on this basis.

Row identity: measurement_record_id is preserved; the output row set is exactly
the within-lifecycle v3c row set in the same order.
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

from degradation_eval import ROW_ID_COL  # noqa: E402
from degradation_eval import add_targets_and_bases  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3C = ROOT / "model_datasets" / "v3c" / "clean_benchmark_pairs.parquet"
V3C_COHORT = ROOT / "model_datasets" / "v3c" / "clean_benchmark_cohort.parquet"
LEDGER = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0" / "engineering_event_ledger.parquet"
OUTPUT = ROOT / "model_datasets" / "v3d"

# nominal horizon -> [lo, hi] evaluation window (days), per 3C plan §10
HORIZON_WINDOWS = {30: (20, 45), 60: (45, 80), 90: (70, 120),
                   180: (140, 240), 365: (300, 450)}
HORIZONS = sorted(HORIZON_WINDOWS)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assign_horizon_band(v: float) -> str:
    """Unique band per row: nearest nominal horizon, tie-broken to smaller H."""
    best_h, best_d = None, 1e18
    for h in HORIZONS:
        lo, hi = HORIZON_WINDOWS[h]
        if lo <= v <= hi:
            d = abs(v - h)
            if d < best_d - 1e-12 or (abs(d - best_d) <= 1e-12
                                      and (best_h is None or h < best_h)):
                best_d = d
                best_h = h
    return f"{best_h}d" if best_h is not None else "other"


def replacement_map() -> dict[int, np.ndarray]:
    """{wheelset_equipment_id: sorted CONFIRMED+LIKELY replacement dates}."""
    led = pd.read_parquet(LEDGER)
    rep = led[(led["event_type"] == "replacement")
              & (led["confidence"].isin(["CONFIRMED", "LIKELY"]))][
        ["wheelset_equipment_id", "event_date"]].dropna()
    if rep.empty:
        return {}
    rep["wid"] = rep["wheelset_equipment_id"].astype("int64")
    ev = pd.to_datetime(rep["event_date"]).to_numpy(dtype="datetime64[us]")
    wids = rep["wid"].to_numpy()
    return {k: np.sort(ev[wids == k]) for k in np.unique(wids)}


def build() -> pd.DataFrame:
    wes = pd.read_parquet(V3C)
    wes = wes[wes["within_lifecycle"]].copy().reset_index(drop=True)
    wes = add_targets_and_bases(wes)

    # frozen cohort split (identifiers preserved; no reordering of test rows)
    coh = pd.read_parquet(V3C_COHORT)
    if not coh[ROW_ID_COL].is_unique:
        raise ValueError("frozen cohort has duplicate row ids")
    wes = wes.merge(coh, on=ROW_ID_COL, how="left")
    n_na = int(wes["split"].isna().sum())
    if n_na:
        raise ValueError(f"{n_na} v3d rows missing from the frozen cohort")

    wes["horizon_window"] = wes["interval_days"].map(assign_horizon_band)
    wes["horizon_days"] = wes["horizon_window"].map(
        lambda w: int(w[:-1]) if w != "other" else None).astype("Int64")

    rep_map = replacement_map()
    t_arr = pd.to_datetime(wes["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    pw = wes["wheelset_equipment_id"].astype("int64").to_numpy()
    for h in HORIZONS:
        flag = np.zeros(len(wes), dtype=bool)
        for i in range(len(wes)):
            dts = rep_map.get(pw[i])
            if dts is None or len(dts) == 0:
                continue
            i0 = np.searchsorted(dts, t_arr[i], side="right")
            if i0 < len(dts) and dts[i0] <= t_arr[i] + np.timedelta64(h, "D"):
                flag[i] = True
        wes[f"replacement_before_{h}d"] = flag

    assert len(wes) == len(wes[ROW_ID_COL].unique()), "row ids duplicated"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "forecast_horizon_benchmark_pairs.parquet"
    wes.to_parquet(out_path, index=False)

    band_counts = {w: int((wes["horizon_window"] == w).sum())
                   for w in ["30d", "60d", "90d", "180d", "365d", "other"]}
    with_before = {f"replacement_before_{h}d": int(wes[f"replacement_before_{h}d"].sum())
                   for h in HORIZONS}

    manifest = {
        "dataset": "forecast_horizon_benchmark_pairs",
        "version": "1.0.0",
        "inputs": {
            "v3c_pairs": str(V3C.relative_to(ROOT)),
            "v3c_pairs_sha256": _sha256(V3C),
            "v3c_cohort": str(V3C_COHORT.relative_to(ROOT)),
            "v3c_cohort_sha256": _sha256(V3C_COHORT),
            "ledger": str(LEDGER.relative_to(ROOT)),
            "ledger_sha256": _sha256(LEDGER),
        },
        "output_sha256": _sha256(out_path),
        "rows": int(len(wes)),
        "equipment": int(wes["wheelset_equipment_id"].nunique()),
        "within_lifecycle_rows": int(wes["within_lifecycle"].sum()),
        "band_counts": band_counts,
        "replacement_before_counts": with_before,
        "row_identity_col": ROW_ID_COL,
        "horizon_windows": {str(h): list(HORIZON_WINDOWS[h]) for h in HORIZONS},
        "banding_algorithm": "nearest nominal horizon; tie broken to smaller window; unresolved rows -> other (train-only)",
        "replacement_before_horizon": "Event Ledger CONFIRMED+LIKELY replacement inside (measurement_time, measurement_time+H]; censoring flag, no row drop",
        "distance": "native NaN preserved + distance_available flag; no imputation",
    }
    (OUTPUT / "forecast_horizon_manifest_v1.0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    print(OUTPUT.relative_to(ROOT))
    return wes


if __name__ == "__main__":
    build()