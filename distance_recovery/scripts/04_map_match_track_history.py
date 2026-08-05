"""Map-match FOIS track history to open network -> per-loco movement distances.

Input: the full `view_locolocation_trackhistory` WAP7 extract as parquet with
columns LocoNumber, Station, LastLocationTime (TrainNo, ZonCode, DivCode
optional). See sql/extract_fois_trackhistory.sql for the extraction query.

If the extract is absent, runs in SAMPLE mode with a synthetic WAP7-style route
so the pipeline is testable end to end.

Outputs under data/processed/:
  fois_transition_distances.parquet   per-loco consecutive-station transitions
                                      with geo_km / rail_km / flags
  fois_loco_daily_distance.parquet    per-loco per-day totals (rail+geo, km)
  fois_mapping_report.md              coverage + sanity metrics

Usage:
  python scripts/04_map_match_track_history.py [--track-history PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _geo import haversine_km  # noqa: E402


def _load_script(name: str, rel_path: Path):
    """Load a numbered sibling script as a module (0X_ prefix is not a valid module name)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_compute = _load_script("compute_distances", Path("03_compute_distances.py"))
load_reference = _compute.load_reference
pair_distances = _compute.pair_distances
snap_stations = _compute.snap_stations

SETTINGS = json.loads((PROJECT_ROOT / "configs" / "settings.json").read_text(encoding="utf-8"))
PROC = PROJECT_ROOT / "data" / "processed"
REPORTS = PROJECT_ROOT / "reports"
STATIONS = None

SAMPLE_TRAIN = "11058"  # ASR->...->Kolkata line, 82 stops, ~2046 km (real timetable sequence)


def _norm(code) -> str:
    return str(code).strip().upper() if pd.notna(code) else ""


def load_track_history(path: Path | None) -> pd.DataFrame:
    if path and Path(path).exists():
        df = pd.read_parquet(path)
        rename = {"LocoNumber": "loco", "Station": "station", "LastLocationTime": "location_time",
                  "TrainNo": "train_no", "ZonCode": "zone", "DivCode": "div"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        df["station"] = df["station"].map(_norm)
        return df

    print("NOTE: FOIS track-history extract not found -> running in SAMPLE mode "
          f"(synthetic WAP7 routes). Place the real extract at {path or SETTINGS['track_history_parquet']} "
          "to reproduce with production data.")
    return synthetic_track_history()


def _sample_route() -> tuple[list[str], list[tuple[str, float]]]:
    """Real consecutive-station sequence (station, hop_km) from a timetable train."""
    ts = pd.read_parquet(PROC / "timetable_stations.parquet")
    stations = pd.read_parquet(PROC / "stations.parquet")[["code"]]
    known = set(stations["code"])
    sub = ts[(ts["train_no"] == SAMPLE_TRAIN) & (ts["cum_km"].notna())].sort_values("seq")
    km_of = dict(zip(sub["station"], sub["cum_km"]))
    seq = [c for c in sub["station"] if c in known]
    hops = []
    prev = seq[0]
    for i in range(1, len(seq)):
        d = km_of[seq[i]] - km_of[prev]
        hops.append((seq[i], max(float(d), 1.0)))
        prev = seq[i]
    return seq, hops


def synthetic_track_history() -> pd.DataFrame:
    seq, hops = _sample_route()
    rows = []
    rng = np.random.default_rng(7)
    locos = [f"30{i:03d}" for i in (201, 202, 205, 214, 220)]
    for li, loco in enumerate(locos):
        n_loops = 3
        t = pd.Timestamp("2026-01-10 08:00") + pd.Timedelta(days=li * 3)
        for loop in range(n_loops):
            route = hops if loop % 2 == 0 else list(reversed(hops))
            prev_station = seq[0] if loop % 2 == 0 else seq[-1]
            rows.append({"loco": loco, "station": prev_station, "location_time": t,
                         "train_no": SAMPLE_TRAIN, "zone": "NR", "div": "DLI"})
            t += pd.Timedelta(hours=2)
            for code, hop_km in route:
                rows.append({"loco": loco, "station": code, "location_time": t,
                             "train_no": SAMPLE_TRAIN, "zone": "NR", "div": "DLI"})
                t += pd.Timedelta(minutes=int(hop_km / 45.0 * 60 + 5))
            t += pd.Timedelta(hours=4)
        # shed stabling: one station, repeated, tiny hop -> sub-20 km day
        t += pd.Timedelta(hours=6)
        for _ in range(3):
            rows.append({"loco": loco, "station": "ASR", "location_time": t,
                         "train_no": SAMPLE_TRAIN, "zone": "NR", "div": "DLI"})
            t += pd.Timedelta(hours=8)
        # shed-internal maintenance shuttle (single short hop => <20 km day)
        t += pd.Timedelta(hours=4)
        rows.append({"loco": loco, "station": "JNL", "location_time": t,
                     "train_no": SAMPLE_TRAIN, "zone": "NR", "div": "DLI"})
        t += pd.Timedelta(hours=12)
    df = pd.DataFrame(rows)
    df["station"] = df["station"].map(_norm)
    return df


def build_transitions(df: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Vectorised consecutive-station transitions with geo/rail distance.

    Runs in O(n) pandas ops so the full 15.5M-row FOIS extract is feasible.
    """
    global STATIONS
    if STATIONS is None:
        STATIONS = pd.read_parquet(PROC / "stations.parquet")
    st = STATIONS[["code", "lat", "lon"]].set_index("code")

    df = df.sort_values(["loco", "location_time"]).reset_index(drop=True)
    # collapse consecutive same-station rows (shed stays) to keep distance zero
    keep = (df["station"] != df["station"].shift(1)).fillna(True)
    df = df[keep].reset_index(drop=True)

    m = matches.set_index("code")
    df["lat"] = df["station"].map(st["lat"])
    df["lon"] = df["station"].map(st["lon"])
    df["a_edge"] = df["station"].map(m["edge_id"])
    df["a_along"] = df["station"].map(m["along_km"])
    df["a_matched"] = df["station"].map(m["matched"]).fillna(False)

    p = df.shift(1)
    same_loco = df["loco"] == p["loco"]

    geo = pd.Series(haversine_km(df["lat"], df["lon"], p["lat"], p["lon"]), index=df.index)
    geo = geo.mask(~same_loco | df["lat"].isna() | p["lat"].isna())

    same_edge = same_loco & df["a_matched"] & p["a_matched"] & (df["a_edge"] == p["a_edge"])
    along = (df["a_along"] - p["a_along"]).abs()
    rail = along.mask(~same_edge)

    def _r(s):
        return s.round(2).where(s.notna(), None)

    return pd.DataFrame({
        "loco": df["loco"],
        "station_a": p["station"],
        "station_b": df["station"],
        "time_a": p["location_time"],
        "time_b": df["location_time"],
        "geo_km": _r(geo),
        "rail_km": _r(rail),
        "same_edge": same_edge,
        "a_matched": p["a_matched"].astype(bool),
        "b_matched": df["a_matched"].astype(bool),
    }).iloc[1:].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track-history", type=str, default=None,
                    help="path to FOIS track-history parquet (default: data/fois_trackhistory_wap7.parquet)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke test: only read the first N track-history rows (truncates routes)")
    args = ap.parse_args()

    matches = snap_stations(force=args.force)
    th = load_track_history(Path(args.track_history) if args.track_history else PROJECT_ROOT / SETTINGS["track_history_parquet"])
    if args.limit:
        th = th.head(args.limit)
        print(f"NOTE: --limit {args.limit} -> truncated for smoke test (routes cut mid-sequence)")
    print(f"track-history rows: {len(th):,}")

    st = pd.read_parquet(PROC / "stations.parquet")[["code"]]
    mapped = th["station"].isin(set(st["code"]))
    print(f"stations matched to reference: {mapped.mean()*100:.2f}%")

    trans = build_transitions(th, matches)
    trans.to_parquet(PROC / "fois_transition_distances.parquet", index=False)

    daily = trans.dropna(subset=["time_b"]).copy()
    daily["day"] = daily["time_b"].dt.date
    daily["rail_km"] = pd.to_numeric(daily["rail_km"])
    daily["geo_km"] = pd.to_numeric(daily["geo_km"])
    agg = daily.groupby(["loco", "day"]).agg(
        n_transitions=("geo_km", "size"),
        rail_km=("rail_km", "sum"),
        geo_km=("geo_km", "sum"),
        rail_coverage=("rail_km", lambda s: s.notna().mean()),
    ).reset_index()
    agg.to_parquet(PROC / "fois_loco_daily_distance.parquet", index=False)

    same = trans["same_edge"].mean() if len(trans) else 0
    report = [
        "# FOIS track-history map-matching report",
        "",
        f"Track-history rows: {len(th):,} · locos: {th['loco'].nunique():,} · transitions: {len(trans):,}",
        f"Station reference match rate: {mapped.mean()*100:.2f}%",
        f"Transitions on the SAME rail edge (rail_km computed): {same*100:.1f}%",
        "",
        f"Daily aggregation rows (loco x day): {len(agg):,}",
        "",
        "## Rail vs geodesic (transitions with both)",
        "",
    ]
    both = trans.dropna(subset=["rail_km", "geo_km"])
    if len(both):
        ratio = (both["rail_km"] / both["geo_km"].replace(0, np.nan)).dropna()
        report += [
            f"- transitions with rail_km AND geo_km: {len(both):,}",
            f"- median rail/geo ratio: {ratio.median():.2f} (>1 expected: rail >= geodesic)",
            f"- share where rail_km >= geo_km: {(both['rail_km'] >= both['geo_km']).mean()*100:.1f}%",
        ]
    report += [
        "",
        "## Sample transitions",
        "",
        "| loco | station_a | station_b | geo_km | rail_km | same_edge |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for _, r in trans.head(15).iterrows():
        report.append(f"| {r['loco']} | {r['station_a']} | {r['station_b']} | {r['geo_km']} | {r['rail_km']} | {r['same_edge']} |")
    report.append("")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "fois_mapping_report.md").write_text("\n".join(report), encoding="utf-8")

    print(f"transitions -> {PROC / 'fois_transition_distances.parquet'}")
    print(f"daily totals -> {PROC / 'fois_loco_daily_distance.parquet'}")
    print(f"report -> {REPORTS / 'fois_mapping_report.md'}")
    print(trans.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
