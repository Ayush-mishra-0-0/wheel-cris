"""Build the processed reference tables from the raw downloads.

Outputs under data/processed/:
  stations.parquet      station code -> name, lat, lon, state, zone
  rail_edges.parquet    exploded rail line parts -> edge_id, line_id, part_idx,
                        n_points, coords (list of [lat, lon])
  timetable_stations.parquet  train_no, station, seq, cumulative_km
  validation_pairs.parquet    consecutive station pairs with timetable km

Usage: python scripts/02_build_reference.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

RAW = PROJECT_ROOT / "data" / "raw"
PROC = PROJECT_ROOT / "data" / "processed"


def _load_geojson(path: Path) -> dict:
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def build_stations() -> None:
    gj = _load_geojson(RAW / "stations.geojson")
    rows = []
    for ft in gj["features"]:
        p = ft["properties"]
        rows.append({
            "code": str(p.get("code", "")).strip().upper(),
            "name": p.get("name", ""),
            "lat": float(p.get("lat")),
            "lon": float(p.get("long")),
            "state": p.get("state", ""),
            "zone": p.get("zone", ""),
        })
    df = pd.DataFrame(rows).dropna(subset=["lat", "lon"])
    df = df[df["code"] != ""].drop_duplicates(subset=["code"], keep="first")

    override_csv = PROJECT_ROOT / "data" / "station_overrides.csv"
    if override_csv.exists():
        ov = pd.read_csv(override_csv)
        ov = ov.dropna(subset=["lat", "lon"])
        merged = df.set_index("code")
        for _, r in ov.iterrows():
            rec = {"name": r["name"], "lat": r["lat"], "lon": r["lon"],
                   "state": r.get("state", ""), "zone": r.get("zone", "")}
            if r["code"] in merged.index:
                for k, v in rec.items():
                    merged.at[r["code"], k] = v
            else:
                merged.loc[r["code"]] = [rec["name"], rec["lat"], rec["lon"], rec["state"], rec["zone"]]
        df = merged.reset_index()
        print(f"  + applied {len(ov):,} manual station overrides from station_overrides.csv (approximate public coords)")

    df = df.sort_values("code").reset_index(drop=True)
    df.to_parquet(PROC / "stations.parquet", index=False)
    print(f"stations: {len(df):,} (lat/lon present, unique code)")
    print(f"  sample: {df.head(3).to_dict('records')}")


def build_rail_edges() -> None:
    gj = _load_geojson(RAW / "gist_rail_network.geojson")
    edges = []
    eidx = 0
    for fid, ft in enumerate(gj["features"]):
        g = ft["geometry"]
        if g is None:
            continue
        # MultiLineString: coordinates is a list of line parts
        parts = g["coordinates"]
        if g["type"] == "LineString":
            parts = [parts]
        for pidx, part in enumerate(parts):
            if len(part) < 2:
                continue
            coords = [[c[1], c[0]] for c in part]  # geojson is [lon, lat] -> [lat, lon]
            edges.append({
                "edge_id": eidx,
                "line_id": fid,
                "part_idx": pidx,
                "n_points": len(coords),
                "coords": coords,
            })
            eidx += 1
    df = pd.DataFrame(edges)
    df.to_parquet(PROC / "rail_edges.parquet", index=False)
    n_vert = int(df["n_points"].sum())
    print(f"rail edges: {len(df):,} from {gj['features'].__len__()} features; total vertices: {n_vert:,}")
    print(f"  n_points distribution: {df['n_points'].describe()[['min','mean','max']].round(1).to_dict()}")


def build_timetable() -> None:
    raw = json.loads((RAW / "schedules_dict.json").read_text(encoding="utf-8"))
    station_rows = []
    pair_rows = []
    for train_no, stations in raw.items():
        items = sorted(stations.items(), key=lambda kv: int(kv[1].get("Serial_No", 0)))
        prev_code, prev_km = None, None
        for code, meta in items:
            try:
                km = float(str(meta.get("Distance", "")).replace(",", ""))
            except (TypeError, ValueError):
                km = np.nan
            station_rows.append({"train_no": train_no, "station": code, "seq": int(meta.get("Serial_No", 0)), "cum_km": km})
            if prev_code is not None and not np.isnan(km) and not np.isnan(prev_km):
                d = km - prev_km
                if d > 0:
                    pair_rows.append({"train_no": train_no, "station_a": prev_code, "station_b": code, "seq_a": int(meta.get("Serial_No", 0)) - 1, "seq_b": int(meta.get("Serial_No", 0)), "timetable_km": round(d, 2)})
            prev_code, prev_km = code, km

    st = pd.DataFrame(station_rows)
    st.to_parquet(PROC / "timetable_stations.parquet", index=False)
    pairs = pd.DataFrame(pair_rows)
    pairs.to_parquet(PROC / "validation_pairs.parquet", index=False)
    print(f"timetable: {len(st):,} station rows, {len(pairs):,} consecutive positive-distance pairs across {raw.__len__()} trains")


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    build_stations()
    build_rail_edges()
    build_timetable()
    print(f"wrote processed tables -> {PROC}")


if __name__ == "__main__":
    main()
