"""Phase 3F - build the change-space degradation substrate (v3f).

Anchors the frozen Phase 3E within-lifecycle rows (239,684) and adds the Phase
3F target: per-dimension change over the paired interval

    dX_d = target_d - base_d          (mm)

Row identity is preserved: same measurement_record_id set, same order as v3e.
No re-splitting, no new ingestion, no imputation. All censoring / coverage /
lifecycle flags are inherited unchanged.

Output   : model_datasets/v3f/change_space_benchmark.parquet
Manifest : model_datasets/v3f/change_space_manifest_v1.0.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V3E = ROOT / "model_datasets" / "v3e" / "forecast_information_ladder.parquet"
OUTPUT = ROOT / "model_datasets" / "v3f"
ROW_ID_COL = "measurement_record_id"
DIMENSIONS = ["wsmDia", "wsmFlangeThickness", "wsmRoot", "wsmWheelGauge"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build() -> pd.DataFrame:
    wes = pd.read_parquet(V3E)
    n_before = len(wes)
    if not (wes["within_lifecycle"]).all():
        raise ValueError("v3e substrate must be entirely within_lifecycle")

    for d in DIMENSIONS:
        t = wes[f"target_{d}"].to_numpy(dtype=float)
        b = wes[f"base_{d}"].to_numpy(dtype=float)
        dX = t - b
        wes[f"dX_{d}"] = dX

    if not wes[ROW_ID_COL].is_unique:
        raise ValueError("v3e row ids not unique; v3f cannot be anchored")

    # row-identity invariant: v3f row set == v3e row set, same order
    v3e_ids = pd.read_parquet(V3E, columns=[ROW_ID_COL])[ROW_ID_COL].to_numpy()
    v3f_ids = wes[ROW_ID_COL].to_numpy()
    if len(v3f_ids) != len(v3e_ids) or not np.array_equal(v3f_ids, v3e_ids):
        raise ValueError("row-identity assertion FAILED: v3f != v3e (order/ids)")

    assert len(wes) == n_before, "row count changed during build"

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "change_space_benchmark.parquet"
    wes.to_parquet(out_path, index=False)

    dX_stats = {}
    for d in DIMENSIONS:
        v = wes[f"dX_{d}"].dropna()
        dX_stats[d] = {
            "n_valid": int(v.size),
            "mean": round(float(v.mean()), 4) if v.size else None,
            "std": round(float(v.std()), 4) if v.size else None,
            "q01": round(float(np.percentile(v, 1)), 4) if v.size else None,
            "q99": round(float(np.percentile(v, 99)), 4) if v.size else None,
        }

    band_counts = {w: int((wes["horizon_window"] == w).sum())
                   for w in ["30d", "60d", "90d", "180d", "365d", "other"]}

    manifest = {
        "dataset": "change_space_benchmark",
        "version": "1.0.0",
        "phase": "3F",
        "inputs": {
            "v3e_ladder": str(V3E.relative_to(ROOT)),
            "v3e_ladder_sha256": _sha256(V3E),
        },
        "output_sha256": _sha256(out_path),
        "rows": int(len(wes)),
        "equipment": int(wes["wheelset_equipment_id"].nunique()),
        "row_identity": "same measurement_record_id set, same order as v3e (asserted)",
        "target": "dX_d = target_d - base_d (per-dimension change over paired interval, mm)",
        "band_counts": band_counts,
        "dX_summary": dX_stats,
        "censoring": "replacement_before_{H}d / crosses_replacement / lifecycle_segment_id inherited; flagged, never dropped",
        "distance": "native NaN preserved + distance_available flag; no imputation",
    }
    (OUTPUT / "change_space_manifest_v1.0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    print(OUTPUT.relative_to(ROOT))
    return wes


if __name__ == "__main__":
    build()
