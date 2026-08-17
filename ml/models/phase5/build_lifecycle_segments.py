"""Phase 5 Layer 0 - lifecycle segment reconstructor.

Splits each wheelset's measurement stream into lifecycle segments per
docs/contracts/wheel_profile_lifecycle_contract_v1.md.

Turning semantics (established empirically from WES v1.0):
  * turning_record_at_measurement flags a measurement SESSION around a turning —
    on some wheelsets only the post-turn (fresh) row, on others every row. The
    flag alone is therefore not a clean event boundary.
  * A reliable TURN EVENT = a flagged row that shows a material change from the
    previous measurement: diameter cut in [1, 25] mm AND (flange or root) wear
    restored by >= 0.2 mm. The flagged row is the POST-TURN (fresh) state; the
    previous measurement is the PRE-TURN (worn) state.

Segment definition:
  * A segment OPENs at a post-turn (fresh) measurement and CLOSEs at the worn
    measurement just before the next turning / replacement boundary.
  * turn event pre-state = last row of the previous segment (worn),
    post-state   = first row of this segment (fresh).

Replacement boundary: wsmProvDate change or wheel-age reset (new wheel identity);
segments also split there (no wear delta crosses a boundary).

Consumes: model_datasets/v3/wheel_engineering_state_v1.0.parquet (immutable).
Outputs: model_datasets/v5/lifecycle_segments.parquet
         model_datasets/v5/lifecycle_turns.parquet
         model_datasets/v5/lifecycle_segments_manifest.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUT = ROOT / "model_datasets" / "v5"

# quality-gate / plausibility windows (v1.0 spec section 4, artefact removal only)
GATES = {
    "wsmDia": (1000.0, 1100.0),
    "wsmFlange": (0.0, 8.0),          # wear; owner-confirmed interpretation 2026-08-11
    "wsmRoot": (0.0, 30.0),
    "wsmThread": (0.0, 30.0),
    "wsmFlangeThickness": (10.0, 50.0),
    "wsmWheelGauge": (1300.0, 1700.0),
}
SIDE_FIELDS = ["wsmDia", "wsmFlange", "wsmRoot", "wsmThread",
               "wsmFlangeThickness", "wsmWheelGauge"]
# Fields marked SEMANTICS_BLOCKED in v1.0 but interpreted as direct wear under the
# Phase 5 lifecycle contract (owner-confirmed 2026-08-11): gate on value only.
VALUE_GATED_FIELDS = {"wsmFlange", "wsmThread"}
CONTEXT = ["locomotive_id", "LomNumber", "LocoType", "wheel_position_1_12",
           "axle_position_1_6", "wheel_profile_2class", "home_shed",
           "defect_zone", "defect_division"]
TURN_CUT_MIN, TURN_CUT_MAX = 1.0, 25.0
WEAR_RESTORE = 0.2
MAX_INTER_EVENT_DAYS = 180

# P0.2 replacement-candidate rule (config-registry constants; single source of truth).
# A consecutive same-wheelset mean-dia UP-jump >= REPLACEMENT_DIA_JUMP_MM is treated as a
# wheel replacement / state reset ONLY when confirmed by one of:
#   * both raw sides (wsmDia1, wsmDia2) also jump >= threshold, OR
#   * the new (higher) level is sustained by the next same-wheelset measurement within
#     REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM (excludes one-off measurement spikes).
REPLACEMENT_DIA_JUMP_MM = 20.0
REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM = 10.0


def reset_aware_window_base(t_arr, seg_arr, p, window_days, DAY=np.timedelta64(1, "D")):
    """Reset-aware trailing-window base index per anchor position p.

    A trailing-window wear rate is only meaningful when every measurement in
    the window belongs to the SAME lifecycle segment: a turn/replacement inside
    the window mixes pre-turn (worn) and post-turn (restored) levels, so the
    rate looks DECREASING right after a reset (root's documented fast-wear
    corruption). This helper clamps the window base to the anchor's segment
    start:

        base = max(searchsorted(t, t[p] - window_days), segment_start[p])

    A base >= p means the anchor IS the segment's first (fresh) row -> no
    within-segment history, so the caller must emit NaN for the rate.
    """
    lo = np.searchsorted(t_arr, t_arr[p] - np.timedelta64(window_days, "D"), side="left")
    seg_start = np.searchsorted(seg_arr, seg_arr[p], side="left")
    return np.maximum(lo, seg_start)


def side_mean(df: pd.DataFrame, field: str) -> pd.Series:
    lo, hi = GATES[field]
    f1 = df[f"{field}1"].to_numpy(dtype=float)
    f2 = df[f"{field}2"].to_numpy(dtype=float)
    if field in VALUE_GATED_FIELDS:
        g1 = np.isfinite(f1)
        g2 = np.isfinite(f2)
    else:
        g1 = df[f"{field}1_quality"].eq("OBSERVED_VALID").to_numpy()
        g2 = df[f"{field}2_quality"].eq("OBSERVED_VALID").to_numpy()
    v1 = np.where(g1 & np.isfinite(f1) & (f1 >= lo) & (f1 <= hi), f1, np.nan)
    v2 = np.where(g2 & np.isfinite(f2) & (f2 >= lo) & (f2 <= hi), f2, np.nan)
    nv = np.stack([v1, v2], axis=1)
    return pd.Series(np.nanmean(nv, axis=1), index=df.index)


def _dia_jump_replacement_mask(wes: pd.DataFrame) -> np.ndarray:
    """Confirmed replacement candidates from consecutive dia up-jumps (numpy).

    Returns a bool array aligned to `wes` (sorted by wheelset + timestamp) marking
    rows whose mean diameter jumped up >= REPLACEMENT_DIA_JUMP_MM vs the previous
    same-wheelset measurement AND the jump is confirmed (both raw sides rose >= the
    threshold, OR the new level is sustained by the next same-wheelset measurement
    within REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM).
    """
    ws = wes["wheelset_equipment_id"].to_numpy()
    dia = wes["mean_wsmDia"].to_numpy(dtype=float)
    d1 = wes["wsmDia1"].to_numpy(dtype=float)
    d2 = wes["wsmDia2"].to_numpy(dtype=float)
    n = len(wes)
    if n == 0:
        return np.zeros(0, dtype=bool)

    same_ws = np.concatenate([[False], ws[1:] == ws[:-1]])
    jump = np.concatenate([[np.nan], dia[1:] - dia[:-1]])
    cand = same_ws & np.isfinite(jump) & (jump >= REPLACEMENT_DIA_JUMP_MM) & np.isfinite(dia)

    # confirmation A: both raw sides jump >= threshold (wheel pair changed)
    both = np.zeros(n, dtype=bool)
    if cand.any():
        d1_prev = np.concatenate([[np.nan], d1[:-1]])
        d2_prev = np.concatenate([[np.nan], d2[:-1]])
        j1 = d1 - d1_prev
        j2 = d2 - d2_prev
        both = (np.isfinite(d1) & np.isfinite(d1_prev) & (j1 >= REPLACEMENT_DIA_JUMP_MM)
                & np.isfinite(d2) & np.isfinite(d2_prev) & (j2 >= REPLACEMENT_DIA_JUMP_MM))

    # confirmation B: new (higher) level sustained by the next same-wheelset measurement
    sustained = np.zeros(n, dtype=bool)
    idx = np.flatnonzero(cand & ~both)
    if len(idx):
        # next valid same-wheelset mean measurement per row (single backward pass)
        next_idx = np.full(n, -1, dtype=np.int64)
        seen = 0
        for i in range(n - 1, -1, -1):
            if seen and ws[i] == ws[i + 1]:
                if np.isfinite(dia[i + 1]):
                    next_idx[i] = i + 1
                else:
                    nxt = next_idx[i + 1]
                    if nxt != -1:
                        next_idx[i] = nxt
            seen += 1
        for i in idx:
            k = next_idx[i]
            if k != -1 and abs(dia[k] - dia[i]) <= REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM:
                sustained[i] = True

    return cand & (both | sustained)


def compute_boundaries(wes: pd.DataFrame) -> pd.DataFrame:
    """Assign turn_event / replacement / _boundary / seg_id to a WES frame (in place).

    The single source of truth for lifecycle boundaries, shared by:
      - build_lifecycle_segments.py   (segment reconstruction)
      - build_degradation_substrate.py (benchmark substrate)
      - dashboard/backend/features.py (serving extractor)

    Requires `mean_{f}` columns for SIDE_FIELDS to be present (see side_mean) and the
    frame sorted by (wheelset_equipment_id, measurement_timestamp).

    A row is a boundary when it is a turn event OR a replacement, where replacement =
    wsmProvDate change OR wheel-age reset OR a CONFIRMED dia up-jump >=
    REPLACEMENT_DIA_JUMP_MM (the P0.2 fix; see _dia_jump_replacement_mask).
    """
    g = wes.groupby("wheelset_equipment_id", sort=False)
    for f in SIDE_FIELDS:
        wes[f"prev_{f}"] = g[f"mean_{f}"].shift(1)
    wes["prev_ts"] = g["_ts"].shift(1)
    wes["days_prev"] = (wes["_ts"] - wes["prev_ts"]) / np.timedelta64(1, "D")

    cut = wes["prev_wsmDia"] - wes["mean_wsmDia"]
    fl_restore = wes["mean_wsmFlange"].fillna(0) <= wes["prev_wsmFlange"].fillna(0) - WEAR_RESTORE
    rt_restore = wes["mean_wsmRoot"].fillna(0) <= wes["prev_wsmRoot"].fillna(0) - WEAR_RESTORE
    dia_cut = (cut >= TURN_CUT_MIN) & (cut <= TURN_CUT_MAX) & wes["prev_wsmDia"].notna()
    wes["turn_event"] = wes["turn_flag"] & dia_cut & (fl_restore | rt_restore)

    prov = pd.to_datetime(wes["wsmProvDate"])
    wes["_prov_num"] = prov.to_numpy(dtype="datetime64[us]").astype("int64")
    wes["_prov_num"] = wes["_prov_num"].replace(-9223372036854775808, np.nan)
    prov_changed = g["_prov_num"].transform(lambda s: s.notna() & s.ne(s.shift()) & s.shift().notna())
    age = wes["wheel_age_days_proxy"].to_numpy(dtype=float)
    age_reset = (age < 10) & (pd.Series(age).shift() > 90) & \
        (wes["wheelset_equipment_id"].eq(wes["wheelset_equipment_id"].shift()))
    dia_jump = _dia_jump_replacement_mask(wes)
    wes["replacement"] = (prov_changed | age_reset).to_numpy() | dia_jump
    wes["_boundary"] = wes["turn_event"] | wes["replacement"]
    wes["seg_id"] = g["_boundary"].cumsum().astype(int)
    return wes


def build_segments() -> tuple[pd.DataFrame, pd.DataFrame]:
    wes = pd.read_parquet(WES)
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)

    for f in SIDE_FIELDS:
        wes[f"mean_{f}"] = side_mean(wes, f)

    t = pd.to_datetime(wes["measurement_timestamp"])
    wes["_ts"] = t.to_numpy(dtype="datetime64[us]")
    wes["turn_flag"] = wes["turning_record_at_measurement"].eq(1)

    # previous measurement per wheelset (pre candidate for any turn event)
    g = wes.groupby("wheelset_equipment_id", sort=False)
    for f in SIDE_FIELDS:
        wes[f"prev_{f}"] = g[f"mean_{f}"].shift(1)
    wes["prev_ts"] = g["_ts"].shift(1)
    wes["days_prev"] = (wes["_ts"] - wes["prev_ts"]) / np.timedelta64(1, "D")

    # ---- turning event / replacement / segment id (single source: compute_boundaries) ----
    wes = compute_boundaries(wes)

    # ---- turn events table: pre = previous measurement, post = this row ----
    turns_rows = []
    ev = wes[wes["turn_event"]]
    for i, r in ev.iterrows():
        pre_ts = r["prev_ts"]
        post_ts = r["_ts"]
        if pre_ts is pd.NaT or (post_ts - pre_ts) > np.timedelta64(MAX_INTER_EVENT_DAYS, "D"):
            continue
        tr = {"wheelset_equipment_id": r["wheelset_equipment_id"],
              "segment_index": int(r["seg_id"]),
              "pre_ts": pd.Timestamp(pre_ts), "post_ts": pd.Timestamp(post_ts),
              "days_between": float((post_ts - pre_ts) / np.timedelta64(1, "D"))}
        for f in SIDE_FIELDS:
            tr[f"pre_{f}"] = r[f"prev_{f}"]
            tr[f"post_{f}"] = r[f"mean_{f}"]
            tr[f"change_{f}"] = r[f"mean_{f}"] - r[f"prev_{f}"]
        for c in ["locomotive_id", "wheel_position_1_12", "wheel_profile_2class",
                  "home_shed", "defect_zone", "defect_division"]:
            tr[c] = r[c]
        turns_rows.append(tr)
    turns = pd.DataFrame(turns_rows)
    turns["cut_dia"] = turns["pre_wsmDia"] - turns["post_wsmDia"]

    # ---- segments ----
    rows = []
    for (eq, seg), grp in wes.groupby(["wheelset_equipment_id", "seg_id"], sort=False):
        grp = grp.sort_values("_ts")
        first, last = grp.iloc[0], grp.iloc[-1]
        r = {"wheelset_equipment_id": eq, "segment_index": int(seg),
             "n_measurements": int(len(grp)),
             "segment_start_ts": pd.Timestamp(first["_ts"]),
             "segment_end_ts": pd.Timestamp(last["_ts"]),
             "days": float((last["_ts"] - first["_ts"]) / np.timedelta64(1, "D")),
             "opens_at_turn": bool(first["turn_event"]),
             "opens_at_replacement": bool(first["replacement"]),
             "closes_at_turn": bool(last["turn_event"]),
             "n_prior_turns": int(grp["turn_event"].sum()) - int(last["turn_event"])}
        for c in CONTEXT:
            if c == "wheel_profile_2class":
                mo = grp[c].mode()
                r[c] = mo.iloc[0] if mo.size else None
            else:
                r[c] = first[c]
        for f in SIDE_FIELDS:
            r[f"start_{f}"] = first[f"mean_{f}"]
            r[f"end_{f}"] = last[f"mean_{f}"]
            r[f"delta_{f}"] = last[f"mean_{f}"] - first[f"mean_{f}"]
        rows.append(r)
    seg = pd.DataFrame(rows)
    return seg, turns


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    seg, turns = build_segments()
    OUT.mkdir(parents=True, exist_ok=True)
    seg_p = OUT / "lifecycle_segments.parquet"
    turn_p = OUT / "lifecycle_turns.parquet"
    seg.to_parquet(seg_p, index=False)
    turns.to_parquet(turn_p, index=False)
    manifest = {
        "task": "phase 5 lifecycle segment reconstruction",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "n_segments": int(len(seg)),
        "n_turning_events": int(len(turns)),
        "n_wheelsets": int(seg["wheelset_equipment_id"].nunique()),
        "min_segment_days": float(seg["days"].min()) if len(seg) else None,
        "median_segment_days": float(seg["days"].median()) if len(seg) else None,
        "median_turn_cut_mm": float(turns["cut_dia"].median()) if len(turns) else None,
        "turning_events_by_year": turns["pre_ts"].dt.year.value_counts().sort_index().astype(int).to_dict() if len(turns) else {},
        "sha256_segments": _sha256(seg_p),
        "sha256_turns": _sha256(turn_p),
    }
    (OUT / "lifecycle_segments_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=str))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
