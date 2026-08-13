"""Core distance engine + validation against timetable ground-truth.

Distance semantics (EXPERIMENTAL, not a released feature):
  geo_km   = haversine great-circle distance between station coordinates
             (lower-bound estimate; cuts across curves/junctions).
  rail_km  = along-the-rail-network distance between the two stations when both
             snap to the SAME rail edge: |along_A - along_B| of the polyline
             (uses the simplified open network; estimate only).
             NaN when no common edge or either station is unmatched.

CLI:
  python scripts/03_compute_distances.py            # build station matches (cached)
  python scripts/03_compute_distances.py --validate # compare vs timetable km
  python scripts/03_compute_distances.py --pairs pairs.csv  # custom pairs (a,b cols)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from _geo import build_grid_index, candidate_edges, haversine_km, project_point_to_polyline  # noqa: E402

SETTINGS = json.loads((PROJECT_ROOT / "configs" / "settings.json").read_text(encoding="utf-8"))
RAW = PROJECT_ROOT / "data" / "raw"
PROC = PROJECT_ROOT / "data" / "processed"
REPORTS = PROJECT_ROOT / "reports"


def load_reference():
    stations = pd.read_parquet(PROC / "stations.parquet")
    edges_df = pd.read_parquet(PROC / "rail_edges.parquet")
    edges = [np.asarray(c.tolist(), dtype=float) for c in edges_df["coords"]]
    grid = build_grid_index(edges, SETTINGS["grid_cell_degrees"])
    return stations, edges_df, edges, grid


def _snap_one(lat, lon, edges, grid):
    best = None
    for eidx in candidate_edges(lat, lon, grid, SETTINGS["grid_cell_degrees"]):
        dist_km, along_km = project_point_to_polyline(lat, lon, edges[eidx])
        if best is None or dist_km < best[0]:
            best = (dist_km, along_km, eidx)
    if best is None or best[0] > SETTINGS["max_match_radius_km"]:
        return {"matched": False, "edge_id": None, "along_km": None, "match_dist_km": None}
    return {"matched": True, "edge_id": int(best[2]), "along_km": best[1], "match_dist_km": round(best[0], 3)}


def snap_stations(force: bool = False) -> pd.DataFrame:
    out = PROC / "station_matches.parquet"
    if out.exists() and not force:
        return pd.read_parquet(out)
    stations, edges_df, edges, grid = load_reference()
    rows = []
    for _, s in stations.iterrows():
        m = _snap_one(s["lat"], s["lon"], edges, grid)
        rows.append({"code": s["code"], "lat": s["lat"], "lon": s["lon"], **m})
    df = pd.DataFrame(rows)
    df.to_parquet(out, index=False)
    matched = df["matched"].mean()
    print(f"station matches: {len(df):,} total, {matched*100:.1f}% snapped to a rail edge within {SETTINGS['max_match_radius_km']} km")
    return df


def pair_distances(pairs: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """pairs needs columns station_a, station_b. Returns df with geo_km, rail_km, match flags."""
    ma = matches.set_index("code")
    recs = []
    for _, r in pairs.iterrows():
        a = ma.index.get_loc(r["station_a"]) if r["station_a"] in ma.index else None
        b = ma.index.get_loc(r["station_b"]) if r["station_b"] in ma.index else None
        geo = np.nan
        rail = np.nan
        same_edge = False
        if a is not None and b is not None:
            A, B = ma.iloc[a], ma.iloc[b]
            geo = haversine_km(A["lat"], A["lon"], B["lat"], B["lon"])
            if A["matched"] and B["matched"] and A["edge_id"] == B["edge_id"]:
                rail = abs(A["along_km"] - B["along_km"])
                same_edge = True
        recs.append({
            "station_a": r["station_a"], "station_b": r["station_b"],
            "geo_km": round(geo, 2) if not np.isnan(geo) else None,
            "rail_km": round(rail, 2) if not np.isnan(rail) else None,
            "same_edge": same_edge,
            "a_matched": bool(a is not None and ma.iloc[a]["matched"]),
            "b_matched": bool(b is not None and ma.iloc[b]["matched"]),
        })
    return pd.DataFrame(recs)


def validate() -> None:
    pairs = pd.read_parquet(PROC / "validation_pairs.parquet")
    matches = snap_stations()
    res = pair_distances(pairs, matches)
    res = res.merge(pairs[["train_no", "station_a", "station_b", "timetable_km"]].drop_duplicates(),
                    on=["station_a", "station_b"], how="left")
    matched = res.dropna(subset=["rail_km", "timetable_km"]).copy()
    matched["err_pct"] = (matched["rail_km"] - matched["timetable_km"]) / matched["timetable_km"] * 100
    matched["err_km"] = matched["rail_km"] - matched["timetable_km"]

    geo = res.dropna(subset=["geo_km", "timetable_km"]).copy()
    geo["err_pct"] = (geo["geo_km"] - geo["timetable_km"]) / geo["timetable_km"] * 100

    n_pair = len(res)
    n_matched = len(matched)
    print(f"validation pairs: {n_pair:,}; with rail_km+timetable: {n_matched:,} ({n_matched/n_pair*100:.1f}%)")

    report = [
        "# Distance validation vs timetable ground-truth",
        "",
        f"Pairs evaluated: {n_pair:,} (consecutive stations with positive timetable km across {pairs['train_no'].nunique():,} trains).",
        f"Both stations snapped to the SAME rail edge: {n_matched:,} ({n_matched/n_pair*100:.1f}%).",
        "",
        "## Rail-matched distance vs timetable km",
        "",
        f"- median |% error|: {matched['err_pct'].abs().median():.2f}%",
        f"- mean |% error|: {matched['err_pct'].abs().mean():.2f}%",
        f"- median |km error|: {matched['err_km'].abs().median():.2f} km",
        f"- pairs within 10%: {(matched['err_pct'].abs() <= 10).mean()*100:.1f}%",
        f"- pairs within 25%: {(matched['err_pct'].abs() <= 25).mean()*100:.1f}%",
        f"- Spearman(rail_km, timetable_km): {matched['rail_km'].corr(matched['timetable_km'], method='spearman'):.3f}",
        "",
        "## Geodesic distance vs timetable km (reference — should be a lower bound)",
        "",
        f"- median |% error|: {geo['err_pct'].abs().median():.2f}%",
        f"- median % bias: {geo['err_pct'].median():+.2f}%",
        f"- Spearman(geo_km, timetable_km): {geo['geo_km'].corr(geo['timetable_km'], method='spearman'):.3f}",
        "",
        "## Worst 10 rail-matched errors (station_a -> station_b, rail vs timetable)",
        "",
        "| station_a | station_b | rail_km | timetable_km | err_km | err_pct |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for _, r in matched.reindex(matched["err_km"].abs().sort_values(ascending=False).index).head(10).iterrows():
        report.append(f"| {r['station_a']} | {r['station_b']} | {r['rail_km']:.1f} | {r['timetable_km']:.1f} | {r['err_km']:+.1f} | {r['err_pct']:+.1f}% |")
    report += [
        "",
        "## Interpretation",
        "",
        "- rail_km improves on geodesic where the network is aligned to real routes;",
        "  the simplified open network has coarse vertices, so absolute rail_km is an",
        "  ESTIMATE (EXPERIMENTAL_NOT_RELEASED), not authoritative chainage.",
        "- pairs that do not snap to the same edge (different lines, yards, halts) fall",
        "  back to geo_km and are flagged (same_edge=False) rather than invented.",
        "- Validation uses timetable cumulative km as an independent cross-check only.",
        "",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "distance_validation_report.md").write_text("\n".join(report), encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        axes[0].scatter(matched["timetable_km"], matched["rail_km"], s=6, alpha=0.4)
        lim = [0, max(matched["timetable_km"].max(), matched["rail_km"].max()) * 1.05]
        axes[0].plot(lim, lim, "r--", label="ideal")
        axes[0].set_xlabel("timetable km"); axes[0].set_ylabel("rail-matched km")
        axes[0].set_title("rail-matched vs timetable"); axes[0].legend()
        axes[1].hist(matched["err_pct"].clip(-100, 100), bins=60)
        axes[1].set_xlabel("% error (rail - timetable)"); axes[1].set_title("rail-matched error distribution")
        fig.tight_layout()
        fig.savefig(REPORTS / "distance_validation.png", dpi=110)
        print(f"plot -> {REPORTS / 'distance_validation.png'}")
    except Exception as e:  # plotting is optional
        print("plot skipped:", e)

    print(f"report -> {REPORTS / 'distance_validation_report.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="validate against timetable ground-truth")
    ap.add_argument("--force", action="store_true", help="rebuild station matches")
    ap.add_argument("--pairs", type=str, help="CSV with station_a, station_b columns; writes pair_distances.parquet")
    args = ap.parse_args()

    snap_stations(force=args.force)
    if args.validate:
        validate()
    if args.pairs:
        pairs = pd.read_csv(args.pairs)
        res = pair_distances(pairs, snap_stations())
        out = PROC / "pair_distances.parquet"
        res.to_parquet(out, index=False)
        print(f"wrote {len(res):,} pair distances -> {out}")


if __name__ == "__main__":
    main()
