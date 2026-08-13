"""Cross-validate RTIS movement records against FOIS location reports.

Question being answered: does the sequence of RTIS divisions/stations for a
loco-day agree with the independently-reported FOIS sequence? High agreement =
RTIS records reflect real operational movement, not reporting artifacts.

Input contracts (parquet):

  --paired PATH        from extract_rtis_fois_crosscheck.sql. Each row has BOTH
                       the RTIS event and the FOIS report for the same loco:
                         loco, rtis_time, rtis_zone, rtis_division,
                         rtis_station, rtis_lat_scaled, rtis_lon_scaled,
                         fois_time, fois_zone, fois_division, fois_station

  --rtis-mileage PATH  internal-plausibility mode on the RTIS feed alone
                       (data/silver/rtis_mileage.parquet): per loco-day division
                       sequence statistics from columns
                       loco_number, event_timestamp, RlkdDivision.

Checks:
  A. Row-level division agreement      RTISDvsn == FOISDvsn
  B. Row-level station agreement       RTISSttn == FOISSttn
  C. Row-level geo plausibility        distance(RTIS lat/lon, FOIS station) <= threshold
  D. Loco-day division-sequence        RTIS division sequence == FOIS division sequence
     agreement                         (ordered by each feed's own timestamp)
  E. Loco-day station-sequence         RTIS station sequence == FOIS station sequence
     agreement

If --paired is absent, runs in SAMPLE mode with synthetic paired data plus the
--rtis-mileage local evidence if available.

Usage:
  python scripts/05_validate_rtis_vs_fois.py --paired data/rtis_fois_paired.parquet
  python scripts/05_validate_rtis_vs_fois.py --rtis-mileage ../../data/silver/rtis_mileage.parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _geo import haversine_km  # noqa: E402

SETTINGS = json.loads((PROJECT_ROOT / "configs" / "settings.json").read_text(encoding="utf-8"))
PROC = PROJECT_ROOT / "data" / "processed"
REPORTS = PROJECT_ROOT / "reports"
GEO_TOLERANCE_KM = SETTINGS.get("geo_plausibility_tolerance_km", 25.0)

_DIVS = {"DDU", "DLI", "PRYJ", "JHS", "ET", "BSL", "KYN", "BCT", "AGT", "BWN", "MAS", "SC", "GTL", "NZM", "CNB", "MB", "LKO", "BTE"}


def _collapse(seq: list[str]) -> list[str]:
    out = []
    for s in seq:
        s = str(s).strip().upper()
        if not s:
            continue
        if not out or out[-1] != s:
            out.append(s)
    return out


def _date(v) -> pd.Timestamp:
    return pd.Timestamp(v).normalize()


def _scale_rtis_coords(df: pd.DataFrame) -> pd.DataFrame:
    """RTIS lat/lon are scaled ints (typically degrees * 1e7). Auto-detect and convert to degrees."""
    out = df.copy()
    for col in ("rtis_lat_scaled", "rtis_lon_scaled"):
        if col in out.columns and out[col].notna().any():
            med = out[col].dropna().abs().median()
            if med > 1000.0:
                out[col] = out[col] / 1e7
    return out


def load_station_coords() -> pd.DataFrame:
    return pd.read_parquet(PROC / "stations.parquet")[["code", "lat", "lon"]].set_index("code")


def check_row_level(df: pd.DataFrame, coords: pd.DataFrame) -> dict:
    n = len(df)
    div_agree = df["rtis_division"].str.strip().str.upper() == df["fois_division"].str.strip().str.upper()
    stn_agree = df["rtis_station"].str.strip().str.upper() == df["fois_station"].str.strip().str.upper()
    out = {
        "rows": n,
        "division_agree_frac": div_agree.mean(),
        "station_agree_frac": stn_agree.mean(),
        "division_agree_n": int(div_agree.sum()),
        "station_agree_n": int(stn_agree.sum()),
    }
    # geo plausibility: RTIS coords vs FOIS station coordinates
    geo = []
    for _, r in df.iterrows():
        lat = r.get("rtis_lat_scaled")
        lon = r.get("rtis_lon_scaled")
        code = str(r.get("fois_station", "")).strip().upper()
        if pd.isna(lat) or pd.isna(lon) or code not in coords.index:
            geo.append(np.nan)
            continue
        s = coords.loc[code]
        geo.append(haversine_km(lat, lon, s["lat"], s["lon"]))
    g = pd.Series(geo)
    out["geo_dist_median_km"] = round(g.median(), 2) if g.notna().any() else None
    out["geo_plausible_frac"] = (g <= GEO_TOLERANCE_KM).mean() if g.notna().any() else None
    out["geo_evaluable_n"] = int(g.notna().sum())
    return out


def _day_sequences(df: pd.DataFrame, time_col: str, value_col: str):
    """Per loco-day, ordered value sequence (collapsed)."""
    df = df.sort_values(["loco", time_col])
    return df.groupby(["loco", df[time_col].map(_date)])[value_col].agg(lambda s: _collapse(list(s)))


def check_sequence_agreement(df: pd.DataFrame, time_a: str, val_a: str, time_b: str, val_b: str) -> dict:
    sa = _day_sequences(df, time_a, val_a)
    sb = _day_sequences(df, time_b, val_b)
    idx = sa.index.intersection(sb.index)
    seq_a = sa.loc[idx]
    seq_b = sb.loc[idx]
    n_days = len(idx)
    eq = seq_a == seq_b
    # days with >= 2 distinct values in BOTH feeds (real movement days)
    multi = (seq_a.map(len) >= 2) & (seq_b.map(len) >= 2)
    return {
        "loco_days": n_days,
        "agree_frac": eq.mean(),
        "agree_n": int(eq.sum()),
        "multi_day_agree_frac": eq[multi].mean() if multi.any() else None,
        "multi_day_n": int(multi.sum()),
    }


def synthetic_paired() -> pd.DataFrame:
    """Plausible paired rows: mostly-consistent RTIS/FOIS with ~8% noise."""
    rng = np.random.default_rng(11)
    st = pd.read_parquet(PROC / "stations.parquet")
    codes = [c for c in ["CSMT", "DR", "TNA", "PNVL", "KJT", "KYN", "IGP", "BSL", "ET", "JHS", "AGC", "NZM"] if c in set(st["code"])]
    div_of = {c: "BCT" for c in codes}
    for c in codes:
        if c in ("IGP", "BSL", "ET"):
            div_of[c] = "ET"
        elif c in ("JHS", "AGC"):
            div_of[c] = "JHS"
        elif c == "NZM":
            div_of[c] = "DLI"
    rows = []
    for li, loco in enumerate(["30201", "30202", "30205", "30214", "30220"]):
        t = pd.Timestamp("2026-01-10 08:00") + pd.Timedelta(days=li * 3)
        for loop in range(3):
            seq = codes if loop % 2 == 0 else list(reversed(codes))
            for code in seq:
                rtis_station = code
                if rng.random() < 0.08:  # RTIS glitch: wrong neighbour station
                    rtis_station = seq[(seq.index(code) + (1 if rng.random() < 0.5 else -1)) % len(seq)]
                rows.append({
                    "loco": loco,
                    "rtis_time": t, "rtis_zone": "CR", "rtis_division": div_of[code],
                    "rtis_station": rtis_station,
                    "rtis_lat_scaled": int(st.set_index("code").loc[code, "lat"] * 1e7),
                    "rtis_lon_scaled": int(st.set_index("code").loc[code, "lon"] * 1e7),
                    "fois_time": t + pd.Timedelta(minutes=5),
                    "fois_zone": "CR", "fois_division": div_of[code], "fois_station": code,
                })
                t += pd.Timedelta(minutes=int(rng.integers(25, 75)))
            t += pd.Timedelta(hours=2)
    return pd.DataFrame(rows)


def rtis_mileage_evidence(path: Path) -> pd.DataFrame:
    """Internal plausibility of the RTIS feed alone (no FOIS) from the silver mileage table."""
    df = pd.read_parquet(path)
    rename = {"loco_number": "loco", "event_timestamp": "rtis_time", "RlkdDivision": "rtis_division"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df = df.dropna(subset=["loco", "rtis_time", "rtis_division"])
    df["rtis_time"] = pd.to_datetime(df["rtis_time"])
    seq = _day_sequences(df, "rtis_time", "rtis_division")
    len_ = seq.map(len)
    ok = seq.map(lambda s: all(x in _DIVS for x in s)) if len(_DIVS) else pd.Series(True, index=seq.index)
    report = {
        "rtis_rows": len(df),
        "rtis_loco_days": len(seq),
        "avg_distinct_divisions_per_day": round(len_.mean(), 2),
        "max_distinct_divisions_in_day": int(len_.max()),
        "days_with_1_division_frac": (len_ == 1).mean(),
        "days_with_gt_4_divisions_frac": (len_ > 4).mean(),
        "day_divisions_all_known_codes_frac": ok.mean(),
    }
    return pd.DataFrame([report])


def render_report(name: str, rows: dict, seq_res: dict, evidence: pd.DataFrame | None) -> Path:
    lines = [
        f"# RTIS vs FOIS cross-validation — {name}",
        "",
        "## Row-level agreement (each paired report)",
        "",
        f"- rows evaluated: {rows['rows']:,}",
        f"- division equality (RTISDvsn == FOISDvsn): {rows['division_agree_frac']*100:.1f}%  ({rows['division_agree_n']:,})",
        f"- station equality (RTISSttn == FOISSttn): {rows['station_agree_frac']*100:.1f}%  ({rows['station_agree_n']:,})",
        f"- RTIS-coords vs FOIS-station geo distance: median {rows['geo_dist_median_km']} km",
        f"- geo-plausible within {GEO_TOLERANCE_KM} km: {rows['geo_plausible_frac']*100:.1f}%  (evaluable {rows['geo_evaluable_n']:,})",
        "",
        "## Loco-day sequence agreement (both feeds report that day)",
        "",
    ]
    for key, label in (("div", "division"), ("stn", "station")):
        r = seq_res[key]
        lines.append(f"- **{label} sequence** ({r['loco_days']:,} loco-days): "
                     f"identical order {r['agree_frac']*100:.1f}%  ({r['agree_n']:,})")
        if r["multi_day_agree_frac"] is not None:
            lines.append(f"  - days with >=2 distinct {label}s in both feeds: {r['multi_day_n']:,} → agreement {r['multi_day_agree_frac']*100:.1f}%")
    if evidence is not None:
        e = evidence.iloc[0]
        lines += [
            "",
            "## RTIS feed internal plausibility (no FOIS needed)",
            "",
            f"- rows: {int(e['rtis_rows']):,} · loco-days: {int(e['rtis_loco_days']):,}",
            f"- avg distinct divisions / loco-day: {e['avg_distinct_divisions_per_day']} (max {int(e['max_distinct_divisions_in_day'])})",
            f"- loco-days with a single division: {e['days_with_1_division_frac']*100:.1f}%",
            f"- loco-days with >4 distinct divisions: {e['days_with_gt_4_divisions_frac']*100:.1f}%",
            f"- loco-days using only known division codes: {e['day_divisions_all_known_codes_frac']*100:.1f}%",
        ]
    lines += [
        "",
        "## Interpretation",
        "",
        "- High division/station equality + high loco-day sequence agreement is",
        "  independent evidence (FOIS is a separate reporting system) that RTIS",
        "  divisions follow real operational movement.",
        "- Geo check validates RTIS coordinates against FOIS station locations,",
        "  so a GPS glitch cannot masquerade as a division move.",
        "- Sequence agreement is order-exact: it also detects shuffled/duplicated",
        "  report artifacts, not just wrong codes.",
        "",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"rtis_fois_crosscheck_{name}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paired", type=str, help="paired RTIS+FOIS parquet (extract_rtis_fois_crosscheck.sql)")
    ap.add_argument("--rtis-mileage", type=str, default=str(PROJECT_ROOT.parent / "data" / "silver" / "rtis_mileage.parquet"),
                    help="silver RTIS mileage parquet for internal plausibility (default: ../../data/silver/rtis_mileage.parquet)")
    args = ap.parse_args()

    coords = load_station_coords()
    evidence = None
    mileage_path = Path(args.rtis_mileage)
    if mileage_path.exists():
        evidence = rtis_mileage_evidence(mileage_path)

    if args.paired and Path(args.paired).exists():
        df = pd.read_parquet(args.paired)
        mode = Path(args.paired).stem
    else:
        print("NOTE: --paired extract not found -> SAMPLE mode with synthetic paired rows.")
        df = synthetic_paired()
        mode = "sample"

    df = _scale_rtis_coords(df)
    for c in ("rtis_time", "fois_time"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])

    rows = check_row_level(df, coords)
    seq_res = {
        "div": check_sequence_agreement(df, "rtis_time", "rtis_division", "fois_time", "fois_division"),
        "stn": check_sequence_agreement(df, "rtis_time", "rtis_station", "fois_time", "fois_station"),
    }
    out = render_report(mode, rows, seq_res, evidence)
    print(f"report -> {out}")
    print(f"  row-level: division {rows['division_agree_frac']*100:.1f}% · station {rows['station_agree_frac']*100:.1f}% · "
          f"geo-plausible {rows['geo_plausible_frac']*100:.1f}%")
    print(f"  loco-day division sequence agreement: {seq_res['div']['agree_frac']*100:.1f}% ({seq_res['div']['agree_n']:,}/{seq_res['div']['loco_days']:,})")
    print(f"  loco-day station  sequence agreement: {seq_res['stn']['agree_frac']*100:.1f}% ({seq_res['stn']['agree_n']:,}/{seq_res['stn']['loco_days']:,})")
    if evidence is not None:
        e = evidence.iloc[0]
        print(f"  RTIS internal: {int(e['rtis_rows']):,} rows, {int(e['rtis_loco_days']):,} loco-days, "
              f"avg {e['avg_distinct_divisions_per_day']} divisions/day")


if __name__ == "__main__":
    main()
