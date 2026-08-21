"""Phase 5 Layer 2 - wear-rate substrate builder (Option 3: rate + integrate).

For every anchor in the FROZEN degradation benchmark (v5, same row set/split and
the exact same point-in-time feature columns), builds the adjacent-pair wear
rate target used by the wear-rate serving head:

    rate_dim = (mean_dim[next same-segment measurement] - mean_dim[anchor])
               / days_between

Because segments split at turn/replacement boundaries, the paired observation
is GUARANTEED to be a within-segment (no-turn) forward step - the exact
"what happens if no turning occurs" regime the 30/90/180 d forecast claims to
answer. The rate model then forecasts value at H = anchor + rate * H, which is
monotone by construction (no cross-horizon consistency violations possible).

Compared with the per-horizon delta heads (whose 180 d targets only exist when
two measurements happen to be ~140-240 days apart in the same segment), this
uses the dense set of adjacent inspections: ~1.3x-3x more training rows and
every horizon shares the same learned rate.

Windowing (documented, not tunable at serve time):
  - span_days in [7, 400]: <7 days is dominated by measurement repeatability
    noise; >400 days is no longer "adjacent" in an operations sense.
  - rate target clipped to +/- RATE_CLIP_MM_PER_DAY (far above the observed
    p99, bounds only pathological bad-pair values).

Output adds per-dim `rate_<dim>` targets + `span_days` + `next_obs_ts_*` to
the frozen benchmark columns. measurement_record_id / split / features are
byte-identical to degradation_benchmark.parquet.
"""
from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from models.phase5.measurement_scope import apply_inspection_scope

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from models.phase5.build_lifecycle_segments import (  # noqa: E402
    GATES, SIDE_FIELDS, compute_boundaries, side_mean,
)

from models.phase5.wes_paths import current_wes_path

WES = current_wes_path()
BENCH = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
SEG = ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet"
OUT = ROOT / "model_datasets" / "v5"

RATE_DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
MIN_SPAN = 7.0
MAX_SPAN = 400.0
RATE_CLIP_MM_PER_DAY = 2.0
DAY = np.timedelta64(1, "D")


def main() -> None:
    bench = pd.read_parquet(BENCH)

    # ---- reconstruct the wheelset stream with segment ids (same as substrate) ----
    wes = pd.read_parquet(WES)
    wes = apply_inspection_scope(wes)
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for f in SIDE_FIELDS:
            wes[f"mean_{f}"] = side_mean(wes, f)
    t = pd.to_datetime(wes["measurement_timestamp"])
    wes["_ts"] = t.to_numpy(dtype="datetime64[us]")
    wes["turn_flag"] = wes["turning_record_at_measurement"].eq(1)
    wes = compute_boundaries(wes)

    eq_arr = wes["wheelset_equipment_id"].to_numpy(dtype="int64")
    t_arr = wes["_ts"].to_numpy()
    seg_arr = wes["seg_id"].to_numpy(dtype="int64")
    val = {f: wes[f"mean_{f}"].to_numpy(dtype=float) for f in RATE_DIMS}
    bounds = np.flatnonzero(np.r_[True, eq_arr[:-1] != eq_arr[1:], True])
    gs, ge = bounds[:-1], bounds[1:]
    grp_eq = eq_arr[gs]
    eq_lookup = {int(e): (s, e_) for e, s, e_ in zip(grp_eq, gs, ge)}

    # anchor identification (bench is a strict subset; 1:1 by measurement_record_id)
    pos_map = dict(zip(wes["measurement_record_id"], np.arange(len(wes), dtype=np.int64)))
    a_eq = bench["wheelset_equipment_id"].to_numpy(dtype="int64")
    a_idx = np.arange(len(bench), dtype=np.int64)
    pos = bench["measurement_record_id"].map(pos_map).to_numpy(dtype="int64")

    n = len(bench)
    span = np.full(n, np.nan)
    next_ts = np.full(n, np.datetime64("NaT", "us"), dtype="datetime64[us]")
    rate = {dim: np.full(n, np.nan) for dim in RATE_DIMS}

    for e in np.unique(a_eq):
        s, en = eq_lookup[int(e)]
        idx = a_idx[a_eq == e]
        if len(idx) == 0:
            continue
        tg = t_arr[s:en]
        sg = seg_arr[s:en]
        v = {dim: val[dim][s:en] for dim in RATE_DIMS}
        p = pos[idx] - s
        has = (p + 1 < len(tg)) & (sg[p + 1] == sg[p])
        sp = np.full(len(p), np.nan)
        if has.any():
            sp[has] = (tg[p[has] + 1] - tg[p[has]]) / DAY
        valid = has & np.isfinite(sp) & (sp >= MIN_SPAN) & (sp <= MAX_SPAN)
        span[idx] = sp
        next_ts[idx[valid]] = tg[p[valid] + 1]
        for dim in RATE_DIMS:
            vv = v[dim]
            ra = np.full(len(p), np.nan)
            vpos = np.flatnonzero(valid)
            ok = np.isfinite(vv[p[vpos]]) & np.isfinite(vv[p[vpos] + 1])
            wp = vpos[ok]
            ra[wp] = (vv[p[wp] + 1] - vv[p[wp]]) / sp[wp]
            ra = np.clip(ra, -RATE_CLIP_MM_PER_DAY, RATE_CLIP_MM_PER_DAY)
            rate[dim][idx] = ra

    for dim in RATE_DIMS:
        bench[f"rate_{dim}"] = rate[dim]
    bench["rate_span_days"] = span
    bench["next_obs_ts"] = next_ts

    path = OUT / "wear_rate_substrate.parquet"
    OUT.mkdir(parents=True, exist_ok=True)
    bench.to_parquet(path, index=False)

    all_rate = np.column_stack([rate[d] for d in RATE_DIMS])
    has_rate = np.isfinite(all_rate).any(axis=1)
    summary = {
        "task": "phase 5 layer 2 wear-rate substrate (Option 3 rate+integrate)",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "output": str(path.relative_to(ROOT)),
        "source_bench": str(BENCH.relative_to(ROOT)),
        "source_wes": str(WES.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": int(len(bench)),
        "rows_train": int(bench["split"].eq("train").sum()),
        "rows_test": int(bench["split"].eq("test").sum()),
        "pairs_with_rate": int(has_rate.sum()),
        "pairs_rate_pct": round(float(has_rate.mean() * 100), 2),
        "min_span_days": MIN_SPAN,
        "max_span_days": MAX_SPAN,
        "rate_clip_mm_per_day": RATE_CLIP_MM_PER_DAY,
        "per_dim": {},
    }
    for dim in RATE_DIMS:
        r = rate[dim]
        fin = r[np.isfinite(r)]
        if len(fin):
            summary["per_dim"][dim] = {
                "n": int(len(fin)),
                "n_train": int(np.isfinite(rate[dim][bench["split"].eq("train").to_numpy()]).sum()),
                "n_test": int(np.isfinite(rate[dim][bench["split"].eq("test").to_numpy()]).sum()),
                "rate_median_mm_per_day": round(float(np.median(fin)), 6),
                "rate_mean_mm_per_day": round(float(np.mean(fin)), 6),
                "rate_p1": round(float(np.percentile(fin, 1)), 5),
                "rate_p99": round(float(np.percentile(fin, 99)), 5),
                "share_lt_0": round(float((r < 0).mean()), 4),
            }
        else:
            summary["per_dim"][dim] = {"n": 0}
    (OUT / "wear_rate_substrate_manifest.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
