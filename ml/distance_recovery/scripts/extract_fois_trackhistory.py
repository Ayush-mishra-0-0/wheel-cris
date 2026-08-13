"""Extract FOIS track history from SQL Server into parquet (chunked, streaming).

Reads connection settings from project .env (DB_SERVER, DB_NAME, DB_USERNAME,
DB_PASSWORD). Writes row-groups incrementally so the full ~88M-row table never
needs to fit in memory.

Options:
  --cohort WAP7       restrict to one loco type (e.g. WAP7 = 15.5M rows)
  --start 2016-01-01  lower bound on LastLocationTime
  --end   2027-01-01  exclusive upper bound on LastLocationTime
  --out PATH          default distance_recovery/data/fois_trackhistory_wap7.parquet
  --chunk 200000      rows fetched per round-trip
  --probe             only print row counts + date range, no extract

Usage:
  python scripts/extract_fois_trackhistory.py --probe
  python scripts/extract_fois_trackhistory.py --cohort WAP7 --start 2016-01-01 --end 2027-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict:
    env = {}
    env_file = PROJECT_ROOT.parent / ".env"
    if not env_file.exists():
        env_file = PROJECT_ROOT / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def connect(env: dict):
    import pyodbc
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={env['DB_SERVER']};"
        f"DATABASE={env['DB_NAME']};"
        f"UID={env['DB_USERNAME']};"
        f"PWD={env['DB_PASSWORD']};"
        f"TrustServerCertificate=yes;Encrypt=no"
    )
    return pyodbc.connect(conn_str, timeout=60)


def probe(conn) -> None:
    def one(sql):
        return pd.read_sql(sql, conn).iloc[0].to_dict()

    print("full view:",
          one("SELECT COUNT_BIG(*) AS rows, CONVERT(char(10),MIN(LastLocationTime),120) AS min_dt, "
              "CONVERT(char(10),MAX(LastLocationTime),120) AS max_dt FROM view_locolocation_trackhistory"))
    print("WAP7 cohort:",
          one("""SELECT COUNT_BIG(*) AS rows, CONVERT(char(10),MIN(LastLocationTime),120) AS min_dt,
                        CONVERT(char(10),MAX(LastLocationTime),120) AS max_dt
                 FROM view_locolocation_trackhistory h
                 INNER JOIN LocoMaster l ON h.LocoNumber = l.LomNumber
                 INNER JOIN LocoTypes lt ON lt.LotId = l.LomType
                 WHERE lt.LotTypeName = 'WAP7'"""))
    print("station populated (full view):",
          one("SELECT COUNT_BIG(*) AS rows, CONVERT(char(10),MIN(LastLocationTime),120) AS min_dt, "
              "CONVERT(char(10),MAX(LastLocationTime),120) AS max_dt FROM view_locolocation_trackhistory "
              "WHERE Station IS NOT NULL AND Station <> ''"))


def extract(conn, cohort: str | None, start: str | None, end: str | None, out: Path, chunk: int) -> None:
    joins = ""
    if cohort:
        joins = ("INNER JOIN LocoMaster l ON h.LocoNumber = l.LomNumber "
                 "INNER JOIN LocoTypes lt ON lt.LotId = l.LomType")
    where = ["h.LastLocationTime IS NOT NULL", "h.Station IS NOT NULL", "h.Station <> ''"]
    if start:
        where.append(f"h.LastLocationTime >= '{start}'")
    if end:
        where.append(f"h.LastLocationTime < '{end}'")
    if cohort:
        where.append(f"lt.LotTypeName = '{cohort}'")
    sql = ("SELECT h.LocoNumber, h.Station, h.LastLocationTime "
           f"FROM view_locolocation_trackhistory h {joins} WHERE " + " AND ".join(where))
    # no ORDER BY: the mapper re-sorts by (loco, time); avoiding a server-side
    # sort over ~15-88M rows keeps the streaming pull fast.

    print("extract SQL:", sql[:300], "...")
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([
        ("LocoNumber", pa.string()), ("Station", pa.string()),
        ("LastLocationTime", pa.timestamp("us")),
    ])
    n = 0
    with pq.ParquetWriter(out, schema, compression="zstd") as writer:
        for df in pd.read_sql(sql, conn, chunksize=chunk):
            df = df[["LocoNumber", "Station", "LastLocationTime"]]
            df.columns = ["LocoNumber", "Station", "LastLocationTime"]
            df["LocoNumber"] = df["LocoNumber"].astype(str)
            df["Station"] = df["Station"].astype(str)
            writer.write_table(pa.Table.from_pandas(df, preserve_index=False, schema=schema))
            n += len(df)
            print(f"  ... {n:,} rows", flush=True)
    print(f"DONE: {n:,} rows -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--cohort", type=str, default=None)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--out", type=str, default=str(PROJECT_ROOT / "data" / "fois_trackhistory_wap7.parquet"))
    ap.add_argument("--chunk", type=int, default=200000)
    args = ap.parse_args()

    env = load_env()
    conn = connect(env)
    print("connected:", env["DB_SERVER"], "/", env["DB_NAME"])
    if args.probe:
        probe(conn)
    else:
        extract(conn, args.cohort, args.start, args.end, Path(args.out), args.chunk)


if __name__ == "__main__":
    main()
