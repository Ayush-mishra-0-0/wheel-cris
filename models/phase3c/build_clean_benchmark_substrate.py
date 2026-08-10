"""Phase 3C - build the clean within-lifecycle degradation benchmark substrate.

Inputs (all frozen/unchanged):
  - model_datasets/v3b/degradation_pairs.parquet  (feature parity; not rebuilt)
  - data/gold/engineering_event_ledger/v1.0/engineering_event_ledger.parquet
  - model_datasets/v2/exposure_features_v2.parquet (approved interval_distance_km)

Adds:
  - crosses_replacement       (ledger replacement strictly inside the pair interval)
  - lifecycle_segment_id      (segment index between replacements per wheelset)
  - distance_*                (from exposure v2 via operational_exposure_id)
  - distance_available flag   (explicit coverage; native NaN preserved, no impute)

Defines the clean within-lifecycle cohort:
      within_lifecycle = ~crosses_reset AND ~crosses_replacement

Outputs (with SHA256 manifest):
  - model_datasets/v3c/clean_benchmark_pairs.parquet
  - model_datasets/v3c/clean_benchmark_manifest_v1.0.json
  - model_datasets/v3c/clean_benchmark_cohort.parquet   (frozen split row ids)

Row identity: measurement_record_id is preserved through every operation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))

from degradation_eval import ROW_ID_COL, add_targets_and_bases, chronological_split  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3B_PAIRS = ROOT / "model_datasets" / "v3b" / "degradation_pairs.parquet"
LEDGER = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0" / "engineering_event_ledger.parquet"
EXPOSURE = ROOT / "model_datasets" / "v2" / "exposure_features_v2.parquet"
OUTPUT = ROOT / "model_datasets" / "v3c"

DISTANCE_COLUMNS = [
    "interval_distance_km", "distance_per_day_km",
    "rtis_distance_coverage_pct_in_interval", "distance_since_turning_km",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ledger_replacement_map() -> dict[int, np.ndarray]:
    """{wheelset_id: sorted array of replacement event datetimes} from the
    governed Event Ledger. Uses CONFIRMED and LIKELY replacements only —
    ANOMALY/UNKNOWN are never coerced into lifecycle boundaries."""
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


def crosses_replacement_mask(pairs: pd.DataFrame,
                             rep_map: dict[int, np.ndarray]) -> np.ndarray:
    """True where a replacement event falls strictly between the pair's current
    and next measurement (lo < evt <= hi)."""
    lo = pd.to_datetime(pairs["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    hi = pd.to_datetime(pairs["next_time"]).to_numpy(dtype="datetime64[us]")
    pw = pairs["wheelset_equipment_id"].astype("int64").to_numpy()
    mask = np.zeros(len(pairs), dtype=bool)
    for i in range(len(pairs)):
        dts = rep_map.get(pw[i])
        if dts is None or len(dts) == 0:
            continue
        i0 = np.searchsorted(dts, lo[i], side="right")
        if i0 < len(dts) and dts[i0] <= hi[i]:
            mask[i] = True
    return mask


def lifecycle_segment_ids(pairs: pd.DataFrame,
                          rep_map: dict[int, np.ndarray]) -> np.ndarray:
    """Per wheelset, the replacement-boundary segment index for each pair's
    CURRENT measurement: 0 before the first replacement, 1 between the first and
    second, etc."""
    pw = pairs["wheelset_equipment_id"].astype("int64").to_numpy()
    t = pd.to_datetime(pairs["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    seg = np.zeros(len(pairs), dtype=int)
    for i in range(len(pairs)):
        dts = rep_map.get(pw[i])
        if dts is None or len(dts) == 0:
            continue
        seg[i] = int(np.searchsorted(dts, t[i], side="right"))
    return seg


def build() -> pd.DataFrame:
    pairs = pd.read_parquet(V3B_PAIRS)
    rep_map = ledger_replacement_map()
    pairs["crosses_replacement"] = crosses_replacement_mask(pairs, rep_map)
    pairs["lifecycle_segment_id"] = lifecycle_segment_ids(pairs, rep_map)

    # distance features via operational_exposure_id (OE-<meas>-<next>)
    exp = pd.read_parquet(EXPOSURE, columns=["operational_exposure_id"] + DISTANCE_COLUMNS)
    oe = "OE-" + pairs[ROW_ID_COL].astype(str) + "-" + pairs["next_record_id"].astype(str)
    pairs["operational_exposure_id"] = oe
    merged = pairs.merge(exp, on="operational_exposure_id", how="left")
    merged["distance_available"] = merged["interval_distance_km"].notna()

    merged["within_lifecycle"] = (~merged["crosses_reset"]) & (~merged["crosses_replacement"])
    merged = add_targets_and_bases(merged)

    # preserve row identity after the left join (merge must not reorder pairs)
    assert merged[ROW_ID_COL].is_unique, "merge duplicated row ids"
    assert set(merged[ROW_ID_COL]) == set(pairs[ROW_ID_COL]), "merge dropped row ids"

    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "clean_benchmark_pairs.parquet"
    merged.to_parquet(out_path, index=False)

    # frozen cohort (chronological 80/20, all arms share these test indices)
    _, tr_mask, te_mask = chronological_split(
        merged, test_frac=0.2, cache_path=OUTPUT / "clean_benchmark_cohort.parquet")

    manifest = {
        "dataset": "clean_benchmark_pairs",
        "version": "1.0.0",
        "inputs": {
            "v3b_pairs": str(V3B_PAIRS.relative_to(ROOT)),
            "v3b_pairs_sha256": _sha256(V3B_PAIRS),
            "ledger": str(LEDGER.relative_to(ROOT)),
            "ledger_sha256": _sha256(LEDGER),
            "exposure_v2": str(EXPOSURE.relative_to(ROOT)),
            "exposure_v2_sha256": _sha256(EXPOSURE),
        },
        "output_sha256": _sha256(out_path),
        "rows": int(len(merged)),
        "equipment": int(merged["wheelset_equipment_id"].nunique()),
        "within_lifecycle_rows": int(merged["within_lifecycle"].sum()),
        "crosses_reset_rows": int(merged["crosses_reset"].sum()),
        "crosses_replacement_rows": int(merged["crosses_replacement"].sum()),
        "distance_available_rows": int(merged["distance_available"].sum()),
        "distance_coverage_pct": round(100.0 * merged["distance_available"].mean(), 2),
        "lifecycle_segments": int(merged["lifecycle_segment_id"].nunique()),
        "row_identity_col": ROW_ID_COL,
        "within_lifecycle_definition": "~crosses_reset AND ~crosses_replacement",
        "replacement_source": "Event Ledger CONFIRMED+LIKELY replacement only; "
                              "ANOMALY/UNKNOWN never coerced into boundaries",
        "distance_source": "approved interval_distance_km (RTIS owner-signed 2026-08-05); "
                           "native NaN preserved + distance_available flag, no imputation",
        "replacement_before_horizon": "added at consumption time per horizon (not precomputed here)",
    }
    (OUTPUT / "clean_benchmark_manifest_v1.0.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    print(OUTPUT.relative_to(ROOT))
    return merged


if __name__ == "__main__":
    build()
