"""Phase 5 Layer 5 - turning-probability substrate (P(turn)).

Anchors = every WES measurement row (full fleet, incl Loco 37597's wheelsets
which the degradation substrate excludes). For each anchor at time t:

  target_H = 1 if a CONFIRMED lifecycle turn (v5 lifecycle_turns) completes
             within (t, t+H] days, 0 if the wheelset is still operating at
             t+H with no turn (a later measurement exists after t+H).

Censoring: an anchor is EXCLUDED when no turn and no later measurement exist
in the horizon (right-censored; no future info). "No future turn observed" is
never read as a guarantee.

Point-in-time discipline:
  * Features use ONLY information available at or before t (trailing windows
    over strictly-prior measurements, segment attrs, shed attribution). The
    row's own measurement never enters its own history window.
  * The future turn is the LABEL only - never a feature.
  * P(turn) = historical maintenance/turning behaviour, NOT engineering-limit
    risk and NOT end-of-life.

Feature computation is VECTORIZED per wheelset (numpy, mirrors the degradation
substrate SLOPE/trajectory loops) so 271k anchors build in seconds.

Rows are subsampled to a bounded size while preserving every wheelset and the
temporal order (keeps each wheelset's latest anchor + a pct of the rest).

Output: model_datasets/v5/turn_probability.parquet + manifest.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

from models.phase5.dashboard.backend.features import (  # noqa: E402
    load_wes, load_segments,
)
from models.phase5.build_lifecycle_segments import SIDE_FIELDS  # noqa: E402

TURNS = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
OUT = ROOT / "model_datasets" / "v5"
DAY = np.timedelta64(1, "D")
HORIZONS = (30, 60, 90)
SEED = 42
TRAIN_CUTOFF = pd.Timestamp("2024-08-12")
MAX_ROWS = 220_000
SLOPE_DIMS = ("wsmFlange", "wsmThread")
RATE_DIMS = (("wsmRoot", (30, 90)), ("wsmDia", (30, 90)))


def load_turns() -> pd.DataFrame:
    t = pd.read_parquet(TURNS)
    t["post_ts"] = pd.to_datetime(t["post_ts"])
    consistent = (
        (t["pre_wsmDia"] > t["post_wsmDia"])
        & (t["pre_wsmFlange"] >= t["post_wsmFlange"])
        & (t["pre_wsmRoot"] >= t["post_wsmRoot"])
        & (t["pre_wsmThread"] >= t["post_wsmThread"]))
    return t[consistent].copy()


def per_wheelset_features(wes_w: pd.DataFrame) -> pd.DataFrame:
    """Vectorized feature frame for one wheelset's measurement stream."""
    w = wes_w.sort_values("measurement_timestamp").reset_index(drop=True)
    t = pd.to_datetime(w["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    n = len(w)
    N = np.arange(n)

    idx = w["measurement_record_id"].to_numpy(dtype="int64")
    eq = int(w.iloc[0]["wheelset_equipment_id"])

    # ---- trailing windows (strictly prior) ----
    km = w["interval_distance_km"].to_numpy(dtype=float)
    km_cum = np.concatenate([[0.0], np.nan_to_num(km).cumsum()])
    av = (~np.isnan(km)).astype(float)
    av_cum = np.concatenate([[0.0], np.cumsum(av)])

    repl = np.flatnonzero(w["replacement"].to_numpy())
    seg_id = w["seg_id"].to_numpy(dtype="int64")
    if len(repl):
        rep_pos = np.searchsorted(repl, N, side="left") - 1
        seg_start_arr = np.where(
            rep_pos >= 0, t_arr[np.maximum(repl[rep_pos], 0)], t_arr[0]).astype("datetime64[us]")
    else:
        seg_start_arr = np.full(n, t_arr[0], dtype="datetime64[us]")

    out = {
        "measurement_record_id": idx,
        "wheelset_equipment_id": np.full(n, eq, dtype="int64"),
        "anchor_ts": t_arr.copy(),
        "_ts": t_arr.copy(),
        "segment_index": seg_id.astype(float),
    }
    for f in SIDE_FIELDS:
        out[f"mean_{f}"] = w[f"mean_{f}"].to_numpy(dtype=float)

    states = {f: w[f"mean_{f}"].to_numpy(dtype=float) for f in SIDE_FIELDS}

    # slope windows are NOT clamped to segment start (extract_features use_first
    # fallback: window reaching before first measurement falls back to it)
    for dim in SLOPE_DIMS:
        st = states[dim]
        for Wd in HORIZONS:
            lo_sl = np.searchsorted(t_arr, t_arr - np.timedelta64(Wd, "D"), side="left")
            use_first = lo_sl >= N
            base = np.where(use_first, 0, lo_sl)
            span = np.where(use_first, (t_arr[N] - t_arr[0]) / DAY,
                            (t_arr[N] - t_arr[np.maximum(lo_sl, 0)]) / DAY)
            chg = st[N] - st[base]
            rd = np.where((np.isfinite(span)) & (span > 0), chg / np.maximum(span, 1e-12), np.nan)
            out[f"ph5_{dim}_rate_per_day_{Wd}d"] = rd

    # km / inspection windows ARE clamped to segment start (v3e accum logic)
    for Wd in HORIZONS:
        low = t_arr - np.timedelta64(Wd, "D")
        eff = np.maximum(low, seg_start_arr)
        lo_idx = np.searchsorted(t_arr, eff, side="left")
        has_prior = lo_idx < N
        lo_safe = np.maximum(lo_idx, 0)
        out[f"inspection_count_{Wd}d"] = np.where(has_prior, N - lo_idx, 0).astype(float)
        out[f"km_last_{Wd}d"] = np.where(has_prior, km_cum[N] - km_cum[lo_safe], np.nan)
        out[f"km_{Wd}d_available"] = (av_cum[N] - av_cum[lo_safe]) > 0

    for dim, windows in RATE_DIMS:
        st = states[dim]
        for Wd in windows:
            lo_idx = np.searchsorted(t_arr, t_arr - np.timedelta64(Wd, "D"), side="left")
            has = lo_idx < N
            span = np.where(has, (t_arr[N] - t_arr[np.maximum(lo_idx, 0)]) / DAY, np.nan)
            out[f"{dim}_rate_per_day_{Wd}d"] = np.where(
                has & (span > 1e-9), (st[N] - st[np.maximum(lo_idx, 0)]) / np.maximum(span, 1e-9), np.nan)

    seg_start_days = np.where(seg_start_arr == t_arr[0], (t_arr[N] - t_arr[0]) / DAY,
                              (t_arr[N] - seg_start_arr) / DAY)
    out["days_since_segment_start"] = seg_start_days
    if n > 1:
        out["days_since_last_inspection"] = np.concatenate([[np.nan], (t_arr[1:] - t_arr[:-1]) / DAY])
    else:
        out["days_since_last_inspection"] = np.full(n, np.nan)

    # scalar fields from WES rows
    for col in ["days_since_turning", "wheel_age_days_proxy",
                "rtis_reporting_coverage_pct", "distance_since_turning_km",
                "distance_per_day_km", "axle_position_1_6",
                "wheel_position_1_12", "wheel_profile_2class"]:
        out[col] = w[col].to_numpy(dtype=float) if col in w.columns else np.full(n, np.nan)
    for col in ["LocoType", "home_shed", "defect_zone"]:
        out[col] = [str(v) if pd.notna(v) else "NA" for v in w[col]]

    df = pd.DataFrame(out)
    df["anchor_ts"] = pd.to_datetime(df["_ts"])
    return df.drop(columns=["_ts"])


def build_substrate() -> pd.DataFrame:
    wes_all = load_wes()  # includes _boundaries(): turn_event, replacement, seg_id
    turns = load_turns()

    turn_by_ws = {}
    for ws, grp in turns.sort_values("post_ts").groupby("wheelset_equipment_id"):
        turn_by_ws[int(ws)] = grp["post_ts"].to_numpy(dtype="datetime64[us]")
    meas_by_ws = {}
    for ws, grp in wes_all.sort_values("measurement_timestamp").groupby("wheelset_equipment_id"):
        meas_by_ws[int(ws)] = grp["measurement_timestamp"].to_numpy(dtype="datetime64[us]")

    panels = []
    for ws, grp in wes_all.groupby("wheelset_equipment_id", sort=False):
        w = int(ws)
        panel = per_wheelset_features(grp)
        if panel.empty:
            continue
        t_arr = panel["anchor_ts"].to_numpy(dtype="datetime64[us]")
        tr_arr = turn_by_ws.get(w, np.array([], dtype="datetime64[us]"))
        meas_arr = meas_by_ws.get(w, t_arr)
        for H in HORIZONS:
            hi = t_arr + np.timedelta64(H, "D")
            n_turn = (np.searchsorted(tr_arr, hi, side="right") -
                      np.searchsorted(tr_arr, t_arr, side="right"))
            later = np.array([np.any(meas_arr > x) for x in hi])
            lab = np.where(n_turn > 0, 1, np.where(later, 0, np.nan))
            panel[f"turned_{H}d"] = lab
            panel[f"_elg_{H}d"] = np.isfinite(lab).astype(int)
        keep = panel.filter(regex="^_elg_").any(axis=1)
        panel = panel[keep]
        if not panel.empty:
            panels.append(panel)

    if not panels:
        raise SystemExit("no usable anchors")
    df = pd.concat(panels, ignore_index=True)
    df["split"] = np.where(df["anchor_ts"] < TRAIN_CUTOFF, "train", "test")
    print(f"anchors (worst-case): {len(df):,}")

    # subsample: keep each wheelset's latest anchor + pct of the rest
    df = df.sort_values(["wheelset_equipment_id", "anchor_ts"]).reset_index(drop=True)
    df["_pos"] = df.groupby("wheelset_equipment_id").cumcount()
    last_pos = df.groupby("wheelset_equipment_id")["_pos"].transform("max")
    last_mask = df["_pos"] == last_pos
    rest = df[~last_mask].copy()
    keep_frac = min(1.0, float(MAX_ROWS) / max(len(rest), 1))
    rng = np.random.default_rng(SEED)
    pid = rng.random(len(rest))
    rest_keep = rest[pid < keep_frac]
    draw = pd.concat([df[last_mask], rest_keep], ignore_index=True)
    if len(draw) > MAX_ROWS:
        draw = draw.sample(n=MAX_ROWS, random_state=SEED).sort_index()

    draw = draw.drop(columns=["_pos"]).reset_index(drop=True)
    print(f"drawn anchors: {len(draw):,}")

    # shed attribution from segments (fallback mirrors extract_features)
    seg = load_segments()
    seg_map = seg[["wheelset_equipment_id", "segment_index", "n_prior_turns",
                   "shed_any"]].drop_duplicates(["wheelset_equipment_id", "segment_index"])
    draw = draw.merge(seg_map,
                      on=["wheelset_equipment_id", "segment_index"], how="left")
    draw["n_prior_turns"] = draw["n_prior_turns"].fillna(draw["segment_index"])
    draw["shed_any"] = draw["shed_any"].fillna("NA")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "turn_probability.parquet"
    draw.to_parquet(path, index=False)

    # base rates on the drawn TEST rows only (honest PIT estimate for display)
    te = draw[draw["split"].eq("test")]
    manifest = {
        "task": "phase 5 layer 5 turning-probability substrate (maintenance behaviour)",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "pointer": "P(turn) = historical maintenance behaviour, NOT engineering-limit risk",
        "n_anchors": int(len(draw)),
        "n_wheelsets": int(draw["wheelset_equipment_id"].nunique()),
        "train_cutoff": str(TRAIN_CUTOFF.date()),
        "split": {"train": int(draw["split"].eq("train").sum()),
                  "test": int(draw["split"].eq("test").sum())},
        "turn_rate_train": {f"turned_{H}d": round(float(draw.loc[draw['split'].eq('train'), f'turned_{H}d'].mean()), 4)
                            for H in HORIZONS},
        "turn_rate_test": {f"turned_{H}d": round(float(te[f"turned_{H}d"].mean()), 4)
                           for H in HORIZONS},
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (OUT / "turn_probability_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    ws37597 = [905685, 905687, 905688, 905689, 905690, 905692]
    print("loco 37597 wheelsets present:",
          sorted(set(draw["wheelset_equipment_id"].tolist()).intersection(ws37597)))
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    build_substrate()