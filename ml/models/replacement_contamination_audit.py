"""P0.2 audit - missed wheel-replacement contamination of degradation targets.

Why: the phase-5 serving degradation models predict "increasing diameter" ~2-3x more often
than it actually occurs (fleet_backtest.json implausibility_diagnostics.wsmDia: model_rate
~12-14% vs actual ~4-6%). Hypothesis: a wheel replacement missed by the turn/replacement
boundary heuristic leaves a post-replacement (larger-diameter) measurement inside the
anchor's "same lifecycle segment", teaching the model that diameter can rise.

This audit quantifies that contamination using the SAME boundary logic the serving
extractor uses (models.phase5.dashboard.backend.features._boundaries), never a copy:

  1. Missed-replacement jump scan (full WES v3): consecutive measurements whose diameter
     jumps up by >= threshold are counted as "detected by boundary" vs "missed".
  2. Target contamination (v5 degradation benchmark): among eligible wsmDia targets, how
     often does the within-segment target exceed the anchor diameter (a physically invalid
     increase) and by how much.
  3. Anchor-level cross-check: of the contaminated targets, how many enclose a missed
     >= threshold diameter jump between anchor and target row.

Run (repo root):
  & "<repo>\\ayush\\Scripts\\python.exe" ml\\models\\replacement_contamination_audit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.phase5.dashboard.backend.features import load_wes  # noqa: E402

BENCH = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
OUT = ROOT / "models" / "experiments" / "v5" / "replacement_contamination_audit.json"

HORIZONS = (30, 90, 180)
JUMP_THRESHOLDS_MM = (15.0, 20.0, 30.0)
DELTA_TOL_MM = 0.05


def scan_missed_replacements(wes: pd.DataFrame, thresholds: tuple[float, ...]) -> dict:
    """Consecutive dia up-jumps vs the serving boundary flags (pure numpy)."""
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    ws = wes["wheelset_equipment_id"].to_numpy()
    dia = wes["mean_wsmDia"].to_numpy(dtype=float)
    flagged = wes["turn_event"].to_numpy(bool) | wes["replacement"].to_numpy(bool)
    res: dict = {
        "rows": int(len(wes)),
        "wheelsets": int(wes["wheelset_equipment_id"].nunique()),
        "boundary_flags": {
            "turn_event": int(wes["turn_event"].sum()),
            "replacement": int(wes["replacement"].sum()),
        },
    }
    if len(dia) > 1:
        same_ws = ws[1:] == ws[:-1]
        jump = dia[1:] - dia[:-1]
        same_seg = wes["seg_id"].to_numpy()[1:] == wes["seg_id"].to_numpy()[:-1]
        for thr in thresholds:
            up = same_ws & (jump >= thr)
            fl = flagged[1:]
            detected = int((up & fl).sum())
            missed = int((up & ~fl).sum())
            res[f"jump_ge_{thr:g}mm"] = {
                "total_up": int(up.sum()),
                "detected_by_boundary": detected,
                "missed_by_boundary": missed,
                "missed_within_same_segment": int((up & ~fl & same_seg).sum()),
                "missed_share": round(missed / max(int(up.sum()), 1), 4),
            }
    return res


def contamination_by_horizon(d: pd.DataFrame) -> dict:
    out: dict = {}
    for H in HORIZONS:
        col = f"tgt_wsmDia_{H}d"
        elig_col = f"eligible_wsmDia_{H}d"
        elig = (
            d[elig_col].astype(bool)
            & np.isfinite(d[col])
            & np.isfinite(d["mean_wsmDia"])
        )
        sub = d.loc[elig]
        if sub.empty:
            out[str(H)] = {"n": 0, "note": "no eligible targets"}
            continue
        delta = sub[col].to_numpy(dtype=float) - sub["mean_wsmDia"].to_numpy(dtype=float)
        pos = delta > DELTA_TOL_MM
        out[str(H)] = {
            "n": int(len(sub)),
            "rate_delta_gt_0.05mm": round(float(pos.mean()), 4),
            "rate_delta_gt_0.5mm": round(float((delta > 0.5).mean()), 4),
            "rate_delta_gt_2mm": round(float((delta > 2.0).mean()), 4),
            "n_delta_gt_0.05mm": int(pos.sum()),
            "median_positive_delta_mm": round(float(np.median(delta[pos])) if pos.any() else np.nan, 4),
            "p99_positive_delta_mm": round(float(np.percentile(delta[pos], 99)) if pos.any() else np.nan, 4),
        }
    return out


def anchor_contains_missed_jump(
    d: pd.DataFrame, wes: pd.DataFrame, thresholds: tuple[float, ...]
) -> dict:
    """Of the contaminated (positive-delta) anchors, how many enclose a missed up-jump?

    All positions are GLOBAL indices into the WES sorted frame. `missed_up[i]` means row i
    is >= min_thr higher than row i-1 and not flagged turn_event/replacement.
    """
    min_thr = min(thresholds)
    wes_s = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    n = len(wes_s)
    ws = wes_s["wheelset_equipment_id"].to_numpy()
    dia = wes_s["mean_wsmDia"].to_numpy(dtype=float)
    flagged = wes_s["turn_event"].to_numpy(bool) | wes_s["replacement"].to_numpy(bool)

    missed_up = np.zeros(n, bool)
    if n > 1:
        same_ws = ws[1:] == ws[:-1]
        jump = dia[1:] - dia[:-1]
        up = np.concatenate([[False], same_ws & (jump >= min_thr)])
        missed_up = up & ~flagged

    ts_global = wes_s["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    ws2pos: dict = {}
    for ws_id in np.unique(ws):
        idx = np.flatnonzero(ws == ws_id)
        ws2pos[int(ws_id)] = (idx, ts_global[idx])
    row2idx = pd.Series(np.arange(n), index=wes_s["measurement_record_id"].to_numpy())

    out: dict = {}
    for H in HORIZONS:
        col = f"tgt_wsmDia_{H}d"
        elig_col = f"eligible_wsmDia_{H}d"
        tgt_ts_col = f"tgt_obs_ts_{H}d"
        elig = d[elig_col].astype(bool) & np.isfinite(d[col]) & np.isfinite(d["mean_wsmDia"])
        sub = d.loc[elig]
        if sub.empty:
            out[str(H)] = {"n": 0}
            continue
        delta = sub[col].to_numpy(dtype=float) - sub["mean_wsmDia"].to_numpy(dtype=float)
        pos_idx = np.flatnonzero(delta > DELTA_TOL_MM)
        anchor_rows = sub.index.to_numpy()[pos_idx]

        contains, miss_pos, miss_total = 0, 0, 0
        for a in anchor_rows:
            r = d.loc[a]
            aidx = row2idx.get(r["measurement_record_id"])
            if aidx is None or pd.isna(r[tgt_ts_col]):
                continue
            pair = ws2pos.get(int(r["wheelset_equipment_id"]))
            if pair is None:
                continue
            idx, tarr = pair
            tpos = int(np.searchsorted(tarr, np.datetime64(pd.Timestamp(r[tgt_ts_col]), "us"), side="left"))
            if tpos >= len(idx) or int(idx[tpos]) <= int(aidx):
                continue
            tpos_g = int(idx[tpos])
            contains += 1
            if missed_up[aidx + 1 : tpos_g + 1].any():
                miss_pos += 1
            miss_total += int(missed_up[aidx + 1 : tpos_g + 1].sum())
        out[str(H)] = {
            "contaminated_anchors_checked": int(contains),
            "contaminated_with_missed_jump": int(miss_pos),
            "share_with_missed_jump": round(miss_pos / max(contains, 1), 4),
            "total_missed_jumps_in_windows": int(miss_total),
        }
    return out


def main() -> None:
    print("Loading WES v3 + exposure (serving boundary logic) ...")
    wes = load_wes()
    print("Loading degradation benchmark ...")
    bench = pd.read_parquet(BENCH)

    audit = {
        "task": "P0.2 replacement-contamination audit",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "boundary_logic": "models.phase5.dashboard.backend.features._boundaries (serving-exact)",
        "date": str(pd.Timestamp.now().date()),
        "missed_replacement_scan": scan_missed_replacements(wes, JUMP_THRESHOLDS_MM),
        "target_contamination": contamination_by_horizon(bench),
        "anchor_cross_check": anchor_contains_missed_jump(bench, wes, JUMP_THRESHOLDS_MM),
        "note": (
            "A 'missed' up-jump >= threshold between consecutive measurements that the serving "
            "boundary heuristic did not flag as turn_event/replacement. Positive-delta targets are "
            "within-segment wsmDia targets exceeding the anchor diameter (physically invalid unless "
            "a replacement happened)."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    print(f"\nWrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
