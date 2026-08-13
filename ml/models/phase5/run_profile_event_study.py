"""Phase 5 Layer 1 - Wheel Profile Lifecycle Event Study.

Studies the wheel-profile lifecycle as evidenced by measurement records:
  1. Trajectories: segment-level wear growth (flange/root/thread) across the fleet.
  2. Turning events: pre-turn state vs limits, cut geometry, days between turns,
     per-shed policy.
  3. Wheel life: time between turns / cut accumulation, and the diameter cost.
  4. Limits adherence: share of turns occurring at/below the contract limits
     (flange 3, root 6, tread 6.5) and shares exceeding them.

Output: models/phase5/report/events_*.png, event_study_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "model_datasets" / "v5"
OUT = ROOT / "models" / "phase5" / "report"

LIMITS = {"wsmFlange": 3.0, "wsmRoot": 6.0, "wsmThread": 6.5}
FLOOR = 1016.0
SAFE = 1020.0


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    seg = pd.read_parquet(V5 / "lifecycle_segments_shed.parquet")
    turns = pd.read_parquet(V5 / "lifecycle_turns_shed.parquet")
    seg["segment_start_ts"] = pd.to_datetime(seg["segment_start_ts"])
    seg["segment_end_ts"] = pd.to_datetime(seg["segment_end_ts"])
    turns["pre_ts"] = pd.to_datetime(turns["pre_ts"])
    if "post_ts" in turns.columns:
        turns["post_ts"] = pd.to_datetime(turns["post_ts"])
    else:
        turns["post_ts"] = turns["pre_ts"]
    return seg, turns


def fig(name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    plt.tight_layout()
    plt.savefig(p, dpi=130, bbox_inches="tight")
    plt.close()
    return p


def plot_trajectories(seg: pd.DataFrame) -> Path:
    # fleet wear growth during segments (start->end), per wear dim
    f, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, dim, lim in zip(axes, ["wsmFlange", "wsmRoot", "wsmThread"], LIMITS.values()):
        st = seg["start_" + dim].to_numpy(dtype=float)
        en = seg["end_" + dim].to_numpy(dtype=float)
        good = np.isfinite(st) & np.isfinite(en)
        st, en = st[good], en[good]
        ax.scatter(st, en, s=4, alpha=0.08, color="#1f77b4")
        mx = max(np.nanmax(st), np.nanmax(en), lim)
        ax.plot([0, mx], [0, mx], ls="--", color="grey", lw=1)
        ax.axvline(lim, color="red", ls=":", lw=1.5)
        ax.axhline(lim, color="red", ls=":", lw=1.5)
        ax.set_title(f"{dim}  (limit {lim}mm)  n={len(st):,}")
        ax.set_xlabel("segment start (mm)"); ax.set_ylabel("segment end (mm)")
        ax.set_xlim(0, mx); ax.set_ylim(0, mx)
    f.suptitle("Wheel wear growth across measurement segments", fontsize=13)
    return fig("events_trajectories.png")


def plot_turn_state(turns: pd.DataFrame) -> Path:
    f, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, dim, lim in zip(axes, ["wsmFlange", "wsmRoot", "wsmThread"], LIMITS.values()):
        pre = turns["pre_" + dim].dropna()
        ax.hist(pre, bins=40, color="#ff7f0e", alpha=0.85)
        ax.axvline(lim, color="red", ls=":", lw=2)
        ax.set_title(f"{dim}: pre-turn wear  n={len(pre):,}  med={pre.median():.2f}")
        ax.set_xlabel("pre-turn (mm)")
        pct = (pre > lim).mean() * 100
        ax.text(0.97, 0.9, f"{pct:.1f}% > {lim}mm", transform=ax.transAxes,
                ha="right", color="red", fontsize=10)
    f.suptitle("Turning-event pre-state vs profile limits", fontsize=13)
    return fig("events_turn_state.png")


def plot_cut_by_shed(turns: pd.DataFrame) -> Path:
    d = turns.dropna(subset=["shed_any", "cut_dia"]).groupby("shed_any")["cut_dia"].agg(
        ["count", "median"]).query("count >= 15").sort_values("median")
    if d.empty:
        return Path("")
    f, ax = plt.subplots(figsize=(11, max(4, len(d) * 0.22)))
    ax.barh(d.index.astype(str), d["median"], color="#2ca02c")
    ax.set_xlabel("median cut (mm)");
    ax.set_title(f"Median cut by shed  (n={len(d)} sheds, >=15 turns)")
    ax.grid(axis="x", alpha=0.3)
    return fig("events_cut_by_shed.png")


def plot_dia_cost(turns: pd.DataFrame) -> Path:
    f, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(turns["cut_dia"].dropna(), bins=50, color="#d62728", alpha=0.9)
    axes[0].set_title(f"Cut size (mm)  med={turns.cut_dia.median():.2f}  n={len(turns):,}")
    axes[0].set_xlabel("post dia - pre dia (negative = cut)")
    # cumulative dia loss across multiple turns per wheelset
    g = turns.groupby("wheelset_equipment_id")["cut_dia"].agg(["count", "sum"])
    g = g[g["count"] >= 2]
    axes[1].hist(g["sum"], bins=40, color="#9467bd", alpha=0.9)
    axes[1].set_title(f"Total dia cut per wheelset (>=2 turns)  n={len(g):,}\nmed={g['sum'].median():.1f}mm")
    axes[1].set_xlabel("cumulative cut (mm)")
    f.suptitle("Diameter cost of turning", fontsize=13)
    return fig("events_dia_cost.png")


def plot_wheel_life(turns: pd.DataFrame) -> Path:
    t = turns.sort_values(["wheelset_equipment_id", "pre_ts"])
    t["prev_turn_ts"] = t.groupby("wheelset_equipment_id")["pre_ts"].shift(1)
    t["inter_turn_days"] = (t["pre_ts"] - t["prev_turn_ts"]).dt.total_seconds() / 86400.0
    gap = t.dropna(subset=["inter_turn_days"])
    gap = gap[gap["inter_turn_days"] > 0]
    multi = gap.groupby("wheelset_equipment_id")["inter_turn_days"].agg(["count", "median"])
    multi = multi[multi["count"] >= 1]
    f, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(gap["inter_turn_days"], bins=80, color="#17becf", alpha=0.9)
    axes[0].set_title(f"Inter-turn gap (days)  med={gap['inter_turn_days'].median():.0f}\n"
                      f"n={len(gap):,} intervals")
    axes[0].set_xlabel("days")
    axes[0].set_xlim(0, gap["inter_turn_days"].quantile(0.98))
    years = multi["median"] / 365.25
    axes[1].hist(years, bins=40, color="#8c564b", alpha=0.9)
    axes[1].set_title(f"Median years between turns per wheelset  n={len(multi):,}\n"
                      f"med={years.median():.2f}")
    axes[1].set_xlabel("years")
    f.suptitle("Turning frequency / wheel life", fontsize=13)
    return fig("events_wheel_life.png")


def main() -> None:
    seg, turns = load()
    paths = {}
    paths["trajectories"] = str(plot_trajectories(seg))
    paths["turn_state"] = str(plot_turn_state(turns))
    paths["cut_by_shed"] = str(plot_cut_by_shed(turns))
    paths["dia_cost"] = str(plot_dia_cost(turns))
    paths["wheel_life"] = str(plot_wheel_life(turns))

    limits = {}
    for dim, lim in LIMITS.items():
        pre = turns["pre_" + dim].dropna()
        limits[dim] = {
            "n": int(len(pre)),
            "median": round(float(pre.median()), 2),
            "p90": round(float(pre.quantile(0.90)), 2),
            "p95": round(float(pre.quantile(0.95)), 2),
            "pct_over_limit": round(float((pre > lim).mean() * 100), 2),
        }
    multi = turns.sort_values(["wheelset_equipment_id", "pre_ts"])
    multi["prev_turn_ts"] = multi.groupby("wheelset_equipment_id")["pre_ts"].shift(1)
    multi["inter_turn_days"] = (multi["pre_ts"] - multi["prev_turn_ts"]).dt.total_seconds() / 86400.0
    multi = multi.dropna(subset=["inter_turn_days"])
    multi = multi[multi["inter_turn_days"] > 0]
    gap_years = multi["inter_turn_days"] / 365.25
    summary = {
        "n_segments": int(len(seg)),
        "n_turning_events": int(len(turns)),
        "n_wheelsets": int(turns["wheelset_equipment_id"].nunique()),
        "n_locos": int(turns["locomotive_id"].nunique()),
        "turning_2024plus": int((turns["post_ts"] >= "2024-01-01").sum()),
        "median_cut_mm": round(float(turns["cut_dia"].median()), 2),
        "median_measurement_gap_days": round(float(turns["days_between"].median()), 0),
        "n_inter_turn_intervals": int(len(multi)),
        "median_inter_turn_years": round(float(gap_years.median()), 2),
        "median_segment_days": round(float(seg["days"].median()), 0),
        "limits": limits,
        "dia": {
            "n_turns_below_floor": int((turns["pre_wsmDia"] <= FLOOR).sum()),
            "n_turns_below_safe": int((turns["pre_wsmDia"] <= SAFE).sum()),
            "median_pre_dia": round(float(turns["pre_wsmDia"].median()), 2),
        },
        "sheds_with_policy": int(turns["shed_any"].notna().sum()),
        "figures": paths,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "event_study_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n",
                                                  encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
