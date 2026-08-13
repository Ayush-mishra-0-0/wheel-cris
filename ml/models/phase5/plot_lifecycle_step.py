"""Plot lifecycle step-series for locomotive wheelset turns.

This script uses the Phase 5 confirmed lifecycle turn table
(model_datasets/v5/lifecycle_turns.parquet) and the v3 wheel engineering state
(model_datasets/v3/wheel_engineering_state_v1.0.parquet) to produce
single-loco, time-series step plots showing wear accumulation, turning
resets, and diameter cut annotations.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TURNS_PATH = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
WES_PATH = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT_DIR = ROOT / "models" / "phase5" / "report" / "lifecycle_step_plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WEAR_DIM_FIELDS = ["wsmRoot", "wsmFlange", "wsmThread"]
DIA_FIELD = "wsmDia"
PLOT_FIELDS = ["mean_wsmRoot", "mean_wsmFlange", "mean_wsmThread", "mean_wsmDia"]
PLOT_LABELS = ["Root wear (mm)", "Flange wear (mm)", "Tread wear (mm)", "Diameter (mm)"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot wheelset lifecycle step plots for one locomotive.")
    parser.add_argument("--loco", required=True, help="Loco number to plot, e.g. 37597")
    parser.add_argument("--wheelset", type=int, default=None, help="Optional specific wheelset_equipment_id to plot")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Directory to save plots and CSVs")
    return parser.parse_args()


def side_mean(df: pd.DataFrame, prefix: str) -> pd.Series:
    return df[[f"{prefix}1", f"{prefix}2"]].astype(float).mean(axis=1)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    turns = pd.read_parquet(TURNS_PATH)
    wes = pd.read_parquet(WES_PATH, columns=[
        "wheelset_equipment_id",
        "measurement_timestamp",
        "LomNumber",
        "wsmDia1",
        "wsmDia2",
        "wsmFlange1",
        "wsmFlange2",
        "wsmRoot1",
        "wsmRoot2",
        "wsmThread1",
        "wsmThread2",
    ])
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    wes["measurement_timestamp"] = pd.to_datetime(wes["measurement_timestamp"])
    for field in ["wsmDia", "wsmFlange", "wsmRoot", "wsmThread"]:
        wes[f"mean_{field}"] = side_mean(wes, field)
    turns["pre_ts"] = pd.to_datetime(turns["pre_ts"])
    turns["post_ts"] = pd.to_datetime(turns["post_ts"])
    return turns, wes


def verify_event_consistency(df: pd.DataFrame) -> pd.DataFrame:
    checks = []
    for _, row in df.iterrows():
        dia_ok = pd.notna(row["pre_wsmDia"]) and pd.notna(row["post_wsmDia"]) and row["pre_wsmDia"] > row["post_wsmDia"]
        flange_ok = pd.notna(row["pre_wsmFlange"]) and pd.notna(row["post_wsmFlange"]) and row["pre_wsmFlange"] >= row["post_wsmFlange"]
        root_ok = pd.notna(row["pre_wsmRoot"]) and pd.notna(row["post_wsmRoot"]) and row["pre_wsmRoot"] >= row["post_wsmRoot"]
        tread_ok = pd.notna(row["pre_wsmThread"]) and pd.notna(row["post_wsmThread"]) and row["pre_wsmThread"] >= row["post_wsmThread"]
        checks.append({
            "wheelset_equipment_id": row["wheelset_equipment_id"],
            "segment_index": row["segment_index"],
            "post_ts": row["post_ts"],
            "dia_ok": dia_ok,
            "flange_ok": flange_ok,
            "root_ok": root_ok,
            "tread_ok": tread_ok,
            "boundary_consistent": dia_ok and flange_ok and root_ok and tread_ok,
        })
    return pd.DataFrame(checks)


def find_measurement_index(rows: pd.DataFrame, ts: pd.Timestamp, field: str, value: float) -> int | None:
    subset = rows[rows["measurement_timestamp"] == ts]
    if len(subset) == 1:
        return int(subset.index[0])
    if len(subset) > 1:
        diffs = (subset[f"mean_{field}"] - value).abs()
        idx = diffs.idxmin()
        return int(idx)
    # fallback to nearest timestamp if exact timestamp match fails
    if len(rows) == 0:
        return None
    idx = (rows["measurement_timestamp"] - ts).abs().idxmin()
    return int(idx)


def plot_wheelset(
    wheelset_id: int,
    loco: str,
    measurements: pd.DataFrame,
    events: pd.DataFrame,
    output_dir: Path,
) -> Path:
    measurements = measurements.sort_values("measurement_timestamp").reset_index(drop=True)
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.subplots_adjust(hspace=0.15)
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"]
    for ax, field, label, color in zip(axes, PLOT_FIELDS, PLOT_LABELS, palette):
        ax.plot(
            measurements["measurement_timestamp"],
            measurements[field],
            marker="o",
            markersize=4,
            linestyle="-",
            color=color,
            alpha=0.8,
            label=label,
        )
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
        # if field != "mean_wsmDia":
        #     ax.invert_yaxis()
    axes[-1].set_xlabel("Measurement timestamp")

    # Split the timeline at the confirmed turning boundaries so the line does not smooth across the reset.
    boundary_indices = []
    event_rows = []
    for event_no, event in enumerate(events.sort_values("post_ts").itertuples(), start=1):
        pre_idx = find_measurement_index(measurements, event.pre_ts, DIA_FIELD, event.pre_wsmDia)
        post_idx = find_measurement_index(measurements, event.post_ts, DIA_FIELD, event.post_wsmDia)
        if pre_idx is None or post_idx is None:
            continue
        boundary_indices.append((pre_idx, post_idx, event_no, event))
        event_rows.append(event)

    for field, ax in zip(PLOT_FIELDS, axes):
        for pre_idx, post_idx, _, event in boundary_indices:
            x_val = event.post_ts
            y_pre = getattr(event, f"pre_{field.replace('mean_', '')}")
            y_post = getattr(event, f"post_{field.replace('mean_', '')}")
            if pd.notna(y_pre) and pd.notna(y_post):
                ax.vlines(x_val, min(y_pre, y_post), max(y_pre, y_post), color="red", linestyle="--", alpha=0.7, linewidth=1.5)

    for event_no, event in enumerate(events.sort_values("post_ts").itertuples(), start=1):
        if pd.isna(event.pre_wsmDia) or pd.isna(event.post_wsmDia):
            continue
        annotation = (
            f"TURN #{event_no}\n"
            f"pre-flange={event.pre_wsmFlange:.2f} mm\n"
            f"pre-root={event.pre_wsmRoot:.2f} mm\n"
            f"pre-tread={event.pre_wsmThread:.2f} mm\n"
            f"dia cut={event.cut_dia:.2f} mm"
        )
        axes[-1].annotate(
            annotation,
            xy=(event.post_ts, event.post_wsmDia),
            xytext=(0, 40 if (event_no % 2) == 0 else 80),
            textcoords="offset points",
            fontsize=7,
            ha="center",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.9, edgecolor="gray", linewidth=0.5),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.2", color="gray", lw=0.5, alpha=0.7),
        )

    title = f"Loco {loco} wheelset {wheelset_id} lifecycle step plot"
    fig.suptitle(title, fontsize=14, y=0.98)
    fig.autofmt_xdate(rotation=20)
    path = output_dir / f"lifecycle_step_loco_{loco}_wheelset_{wheelset_id}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_combined_flange_vs_dia(
    loco: str,
    wes: pd.DataFrame,
    events: pd.DataFrame,
    output_dir: Path,
) -> Path:
    wheelsets = sorted(events["wheelset_equipment_id"].unique())
    fig, ax1 = plt.subplots(figsize=(16, 9))
    ax2 = ax1.twinx()
    cmap = plt.get_cmap("tab10")
    for index, wheelset_id in enumerate(wheelsets):
        measurements = wes[wes["wheelset_equipment_id"] == wheelset_id].copy()
        if measurements.empty:
            continue
        color = cmap(index % 10)
        ax1.plot(
            measurements["measurement_timestamp"],
            measurements["mean_wsmFlange"],
            marker="o",
            markersize=4,
            linestyle="-",
            color=color,
            alpha=0.8,
            label=f"Flange WS {wheelset_id}",
        )
        wheelset_events = events[events["wheelset_equipment_id"] == wheelset_id].sort_values("post_ts")
        if not wheelset_events.empty:
            ax2.scatter(
                wheelset_events["post_ts"],
                wheelset_events["cut_dia"],
                marker="x",
                color=color,
                s=60,
                label=f"Cut WS {wheelset_id}",
                alpha=0.9,
            )
            for _, event in wheelset_events.iterrows():
                ax1.axvline(event["post_ts"], color=color, linestyle="--", alpha=0.25)

    ax1.set_xlabel("Measurement timestamp")
    ax1.set_ylabel("Flange wear (mm)")
    ax2.set_ylabel("Diameter cut (mm)")
    ax1.grid(alpha=0.25)
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    by_label = dict(zip(labels1 + labels2, handles1 + handles2))
    fig.legend(by_label.values(), by_label.keys(), loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.95))
    fig.suptitle(f"Loco {loco} flange wear vs diameter cut for {len(wheelsets)} wheelsets", fontsize=14, y=0.98)
    fig.autofmt_xdate(rotation=20)
    path = output_dir / f"lifecycle_step_loco_{loco}_combined_flange_dia.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def build_event_table(events: pd.DataFrame, loco: str, wheelset: int | None = None) -> pd.DataFrame:
    table = events.copy()
    table = table.sort_values(["wheelset_equipment_id", "post_ts"]).reset_index(drop=True)
    table["loco"] = loco
    # keep only confirmed lifecycle boundaries: the reset must restore wear DOWN
    # on every dimension (flange/root/tread) while diameter is cut.
    consistent = (
        (table["pre_wsmDia"] > table["post_wsmDia"])
        & (table["pre_wsmFlange"] >= table["post_wsmFlange"])
        & (table["pre_wsmRoot"] >= table["post_wsmRoot"])
        & (table["pre_wsmThread"] >= table["post_wsmThread"]))
    table = table[consistent].copy()
    table["turn_no"] = table.groupby("wheelset_equipment_id").cumcount() + 1
    table = table.rename(columns={
        "post_ts": "turn_date",
        "pre_wsmDia": "pre_dia",
        "post_wsmDia": "post_dia",
        "cut_dia": "dia_cut",
        "pre_wsmFlange": "pre_flange",
        "post_wsmFlange": "post_flange",
        "pre_wsmRoot": "pre_root",
        "post_wsmRoot": "post_root",
        "pre_wsmThread": "pre_tread",
        "post_wsmThread": "post_tread",
    })
    columns = [
        "loco",
        "wheelset_equipment_id",
        "turn_no",
        "turn_date",
        "pre_dia",
        "post_dia",
        "dia_cut",
        "pre_flange",
        "post_flange",
        "pre_root",
        "post_root",
        "pre_tread",
        "post_tread",
        "boundary_consistent",
        "dia_ok",
        "flange_ok",
        "root_ok",
        "tread_ok",
    ]
    table = table.reindex(columns=[c for c in columns if c in table.columns])
    if wheelset is not None:
        table = table[table["wheelset_equipment_id"] == wheelset]
    return table


def main() -> None:
    args = parse_args()
    loco = str(args.loco)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    turns, wes = load_data()
    mapping = (wes[["wheelset_equipment_id", "measurement_timestamp", "LomNumber"]]
               .rename(columns={"measurement_timestamp": "post_ts"})
               .drop_duplicates(["wheelset_equipment_id", "post_ts"], keep="last"))
    turns = turns.merge(mapping, on=["wheelset_equipment_id", "post_ts"], how="left")
    turns["LomNumber"] = turns["LomNumber"].astype("string")

    loco_turns = turns[turns["LomNumber"] == loco].copy()
    if loco_turns.empty:
        raise SystemExit(f"No confirmed lifecycle turns found for loco {loco}.")

    if args.wheelset is not None:
        if args.wheelset not in loco_turns["wheelset_equipment_id"].unique():
            raise SystemExit(
                f"Wheelset {args.wheelset} is not available for loco {loco}."
            )
        loco_turns = loco_turns[loco_turns["wheelset_equipment_id"] == args.wheelset]

    electronics = verify_event_consistency(loco_turns)
    loco_turns = loco_turns.merge(electronics, on=["wheelset_equipment_id", "segment_index", "post_ts"], how="left")
    csv_path = output_dir / f"turn_events_loco_{loco}.csv"
    event_table = build_event_table(loco_turns, loco, args.wheelset)
    event_table.to_csv(csv_path, index=False)
    print(f"Saved event table: {csv_path}")

    bad = event_table[~event_table["boundary_consistent"]]
    if not bad.empty:
        print("WARNING: some confirmed turns are not consistent across diameter/flange/root/tread:")
        print(bad.to_string(index=False))

    # Plot ONLY boundary-consistent events (confirmed lifecycle boundaries).
    loco_turns = loco_turns[loco_turns["boundary_consistent"]].copy()
    if loco_turns.empty:
        raise SystemExit(f"No boundary-consistent confirmed turns remain for loco {loco}.")

    wheelsets = sorted(loco_turns["wheelset_equipment_id"].unique())
    print(f"Plotting loco {loco} with wheelsets {wheelsets}")
    plot_paths = []
    for wheelset_id in wheelsets:
        measurements = wes[wes["wheelset_equipment_id"] == wheelset_id].copy()
        if measurements.empty:
            print(f"Skipping missing measurement timeline for wheelset {wheelset_id}")
            continue
        wheelset_events = loco_turns[loco_turns["wheelset_equipment_id"] == wheelset_id].copy()
        if wheelset_events.empty:
            print(f"Skipping wheelset {wheelset_id} because no confirmed turns remain after filtering")
            continue
        plot_path = plot_wheelset(wheelset_id, loco, measurements, wheelset_events, output_dir)
        plot_paths.append(plot_path)
        print(f"Saved plot: {plot_path}")

    if args.wheelset is None and len(wheelsets) > 1:
        combined_path = plot_combined_flange_vs_dia(loco, wes, loco_turns, output_dir)
        plot_paths.append(combined_path)
        print(f"Saved combined plot: {combined_path}")

    if not plot_paths:
        raise SystemExit(f"No plots were generated for loco {loco}.")

    print("Finished.")


if __name__ == "__main__":
    main()
