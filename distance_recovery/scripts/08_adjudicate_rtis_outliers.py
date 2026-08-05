"""Adjudicate RTIS outlier days using the FOIS-derived reconstructed distance.

07 flagged 3,880 RTIS loco-days (0.29%) as implausible under the safe
aggregation rule. Rule-based rejection is heuristic; this script replaces it
with EVIDENCE: for each flagged day, ask the independent FOIS map-matched
distance (`distance_recovery` reconstruction) whether the RTIS total was real.

Decision table (RTIS candidate vs FOIS recon for the same loco-day):
  ratio = rtis_km / recon_km
    ratio > 2.0                -> CONFIRMED_DOUBLE   RTIS double-counted; use FOIS recon
    ratio < 0.7                -> CONFIRMED_UNDER    RTIS undercounted; use FOIS recon
    0.7 <= ratio <= 1.3        -> CONFIRMED_REAL     RTIS corroborated; keep RTIS
    otherwise                  -> PARTIAL            in-between; manual review
    no FOIS that day           -> UNRESOLVED         no witness; keep flagged, no value

Outputs:
  data/processed/rtis_daily_adjudicated.parquet
  reports/rtis_outlier_adjudication_report.md

Usage:
  python scripts/08_adjudicate_rtis_outliers.py --fois-daily data/processed/fois_loco_daily_distance.parquet
  python scripts/08_adjudicate_rtis_outliers.py --demo     # synthetic overlap to test the classifier
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROC = PROJECT_ROOT / "data" / "processed"
REPORTS = PROJECT_ROOT / "reports"


def load_fois_recon(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["day"] = pd.to_datetime(df["day"])
    df["loco"] = df["loco"].astype(str).str.strip()
    if "recon_km" not in df.columns:
        df["recon_km"] = df["rail_km"].fillna(df["geo_km"])
    return df[["loco", "day", "recon_km"]]


def adjudicate(outliers: pd.DataFrame, fois: pd.DataFrame) -> pd.DataFrame:
    m = outliers.merge(fois, on=["loco", "day"], how="left")
    r = m["rtis_km_candidate"] / m["recon_km"].replace(0, np.nan)
    status = np.where(
        m["recon_km"].isna(), "UNRESOLVED",
        np.where(r > 2.0, "CONFIRMED_DOUBLE",
        np.where(r < 0.7, "CONFIRMED_UNDER",
        np.where(r <= 1.3, "CONFIRMED_REAL", "PARTIAL"))))
    m["status"] = status
    m["ratio"] = r.round(2)
    final = m["rtis_km_candidate"]
    final = final.mask(m["status"].isin(["CONFIRMED_DOUBLE", "CONFIRMED_UNDER"]), m["recon_km"])
    m["rtis_km_adjudicated"] = final.where(m["status"] != "UNRESOLVED")
    return m


def demo_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    days = [pd.Timestamp(d) for d in
            ("2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14",
             "2026-02-01", "2026-02-02")]
    outliers = pd.DataFrame({
        "loco": ["30201"] * 5 + ["30202"] * 2,
        "day": days,
        "rtis_km_candidate": [5154.6, 3400.0, 1200.0, 900.0, 600.0, 3200.0, 100.0],
        "outlier_flag": [True] * 7,
    })
    fois = pd.DataFrame({
        "loco": ["30201"] * 5 + ["30202"] * 2,
        "day": days,
        "recon_km": [490.0, 520.0, 1000.0, 980.0, 620.0, 800.0, 95.0],
    })
    return outliers, fois


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fois-daily", type=str, default=str(PROC / "fois_loco_daily_distance.parquet"))
    ap.add_argument("--safe", type=str, default=str(PROC / "rtis_daily_candidate.parquet"),
                    help="candidate frame with outlier_flag (written by 07)")
    ap.add_argument("--demo", action="store_true", help="synthetic overlap to exercise the classifier")
    args = ap.parse_args()

    if args.demo:
        outliers, fois = demo_frame()
        tag = "DEMO (synthetic overlap)"
    else:
        safe = pd.read_parquet(args.safe)
        outliers = safe[safe["outlier_flag"]][["loco", "day", "rtis_km_candidate", "outlier_flag"]].copy()
        fois = load_fois_recon(Path(args.fois_daily))
        tag = "REAL run"

    res = adjudicate(outliers, fois)
    counts = res["status"].value_counts()
    resolved = res[res["status"].isin(["CONFIRMED_DOUBLE", "CONFIRMED_UNDER"])]
    lines = [
        "# RTIS outlier adjudication via FOIS reconstruction",
        "",
        f"Run: {tag}",
        f"Outlier loco-days: {len(res):,}",
        f"Outliers with a FOIS witness that day: {res['status'].ne('UNRESOLVED').sum():,}",
        "",
        "| status | count | meaning |",
        "| --- | ---: | --- |",
    ]
    for s, meaning in (
        ("CONFIRMED_DOUBLE", "RTIS double-counted -> replaced by FOIS recon"),
        ("CONFIRMED_UNDER", "RTIS undercounted -> replaced by FOIS recon"),
        ("CONFIRMED_REAL", "RTIS corroborated by FOIS -> RTIS kept"),
        ("PARTIAL", "in-between -> manual review"),
        ("UNRESOLVED", "no FOIS witness that day -> excluded, never zeroed"),
    ):
        lines.append(f"| {s} | {int(counts.get(s, 0)):,} | {meaning} |")
    lines.append("")
    if len(resolved):
        lines.append(f"Of the resolved outliers, {len(resolved):,} had their RTIS value corrected to the FOIS reconstruction.")
    else:
        lines.append("No outliers were resolved yet (FOIS witness coverage required).")
    lines += [
        "",
        "## Examples",
        "",
        "| loco | day | rtis_km | recon_km (FOIS) | ratio | status | final km |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for _, r in res.head(10).iterrows():
        lines.append(f"| {r['loco']} | {r['day'].date()} | {r['rtis_km_candidate']:,.1f} | "
                     f"{r['recon_km'] if pd.notna(r['recon_km']) else '—'} | {r['ratio']} | {r['status']} | "
                     f"{r['rtis_km_adjudicated']:.1f} |")
    lines.append("")
    REPORTS.mkdir(parents=True, exist_ok=True)
    rep = REPORTS / "rtis_outlier_adjudication_report.md"
    rep.write_text("\n".join(lines), encoding="utf-8")
    PROC.mkdir(parents=True, exist_ok=True)
    res.to_parquet(PROC / "rtis_daily_adjudicated.parquet", index=False)
    print(f"report -> {rep}")
    print(f"  outliers {len(res):,} -> {counts.to_dict()}")
    print(f"  resolved (replaced with FOIS recon): {len(resolved):,}")


if __name__ == "__main__":
    main()
