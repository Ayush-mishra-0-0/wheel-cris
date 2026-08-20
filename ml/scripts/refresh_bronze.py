"""Live Bronze refresh: re-extract the wheel-register stack from SLAM into parquet.

Covers the "Reason Of Turning" provenance pipeline end-to-end:
  1. LocoWheelRegister                (cohort-filtered, extraction SQL, COHORT=WAP7)
  2. WheelSetMeasurements             (full table)
  3. LocoWheelRegister_LwrId_238014_238028     (partition probe/copy)
  4. WheelSetMeasurements_wsmWRId_238014_238028 (partition probe/copy)
  5-10. WheelReadingPurpose, WheelProfile, ScheduleTypes, Sections,
        FunctionalLocations, Employees (lookup decodes)

The main LocoWheelRegister / WheelSetMeasurements tables already contain the
August-2026 rows (LwrId up to 243,612; max LwrUpdatedOn up to 2026-08-20). The
`_LwrId_238014_238028` tables hold only 15/90 rows (July, LwrId 238014-238028) and are
already included inside the main tables, so they are kept as cloned probes for audit.

Reads connection settings from `ml/.env` (DB_SERVER, DB_NAME, DB_USERNAME, DB_PASSWORD).
Streams each query in chunks and writes metadata JSON beside each parquet, matching the
existing Bronze convention (`<table>_metadata.json`).

Usage:
  python ml/scripts/refresh_bronze.py            # full refresh (10 tables)
  python ml/scripts/refresh_bronze.py --no-part   # skip the partition probes
  python ml/scripts/refresh_bronze.py --probe     # only print live row counts / freshness
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BRONZE = ROOT / "data" / "bronze"
SQL = ROOT / "sql" / "extraction"
COHORT = "WAP7"
CHUNK = 200_000


def load_env() -> dict:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
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
    return pyodbc.connect(conn_str, timeout=120)


def probe(conn) -> dict:
    cur = conn.cursor()
    out = {}
    def q(label, sql):
        cur.execute(sql)
        r = cur.fetchone()
        out[label] = {"rows": r[0], "min_dt": str(r[1]) if len(r) > 1 else None,
                      "max_dt": str(r[2]) if len(r) > 2 else None}
    q("LocoWheelRegister_live",
      "SELECT COUNT_BIG(*), MIN(LwrUpdatedOn), MAX(LwrUpdatedOn) FROM LocoWheelRegister")
    q("LocoWheelRegister_WAP7",
      "SELECT COUNT_BIG(*), MIN(LwrUpdatedOn), MAX(LwrUpdatedOn) FROM LocoWheelRegister lwr "
      "INNER JOIN LocoMaster lm ON lm.LomId = lwr.LwrLocoId "
      "INNER JOIN LocoTypes lt ON lt.LotId = lm.LomType WHERE lt.LotTypeName = 'WAP7'")
    q("WheelSetMeasurements_live",
      "SELECT COUNT_BIG(*), MIN(wsmUpdatedOn), MAX(wsmUpdatedOn) FROM WheelSetMeasurements")
    q("WheelSetMeasurements_register_join_WAP7",
      "SELECT COUNT_BIG(*), MIN(wsm.wsmUpdatedOn), MAX(wsm.wsmUpdatedOn) FROM WheelSetMeasurements wsm "
      "INNER JOIN LocoWheelRegister lwr ON lwr.LwrId = wsm.wsmWRId "
      "INNER JOIN LocoMaster lm ON lm.LomId = lwr.LwrLocoId "
      "INNER JOIN LocoTypes lt ON lt.LotId = lm.LomType WHERE lt.LotTypeName = 'WAP7'")
    for part in ["LocoWheelRegister_LwrId_238014_238028",
                 "WheelSetMeasurements_wsmWRId_238014_238028"]:
        try:
            cur.execute(f"SELECT COUNT_BIG(*) FROM {part}")
            out[part] = {"rows": cur.fetchone()[0], "min_dt": None, "max_dt": None}
        except Exception as e:
            out[part] = {"rows": None, "error": str(e)}
    cur.close()
    return out


def stream_to_parquet(conn, sql: str, out: Path, chunk: int = CHUNK) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql(sql, conn)
    df.to_parquet(out, index=False)
    return {"rows": int(len(df)), "columns": len(df.columns),
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2)}


def extract(conn, targets, include_part: bool) -> list[dict]:
    results = []
    for t in targets:
        if not include_part and t["name"].startswith("LocoWheelRegister_LwrId"):
            continue
        if not include_part and t["name"].startswith("WheelSetMeasurements_wsmWRId"):
            continue
        sql = t.get("sql")
        if t.get("sql_file"):
            sql = (SQL / t["sql_file"]).read_text(encoding="utf-8").replace("{{COHORT}}", COHORT)
            sql = sql.strip().rstrip(";")
        assert sql, f"no sql for {t['name']}"
        out = BRONZE / t["out"]
        stat = stream_to_parquet(conn, sql, out)
        meta = {
            "table_name": t["table_name"],
            "source_query": t.get("sql_file", t.get("source_note", "")),
            "rows": stat["rows"],
            "columns": stat["columns"],
            "memory_mb": stat["memory_mb"],
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_database": "SLAM_PROD_DB_10.05.2022",
            "cohort": COHORT if t.get("cohort") else None,
        }
        meta_path = out.with_name(out.stem + "_metadata.json")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        results.append(meta)
        print(f"OK  {t['table_name']}: {stat['rows']:,} rows x {stat['columns']} cols -> {out.name}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="only print live freshness/counts")
    ap.add_argument("--no-part", action="store_true", help="skip partition-probe tables")
    args = ap.parse_args()

    env = load_env()
    conn = connect(env)
    print("connected:", env["DB_SERVER"], "/", env["DB_NAME"])

    if args.probe:
        print(json.dumps(probe(conn), indent=2, default=str))
        return

    targets = [
        {
            "name": "LocoWheelRegister_WAP7",
            "table_name": "LocoWheelRegister",
            "sql_file": "loco_wheel_register.sql",
            "out": "loco_wheel_register.parquet",
            "cohort": True,
        },
        {
            "name": "WheelSetMeasurements_full",
            "table_name": "WheelSetMeasurements",
            "sql": "SELECT * FROM WheelSetMeasurements",
            "source_note": "sql/extraction/wheel_measurements.sql (SELECT *)",
            "out": "wheel_measurements.parquet",
            "cohort": False,
        },
        # Partition probes: proven to be redundant subsets already inside the main tables.
        {
            "name": "LocoWheelRegister_LwrId_238014_238028",
            "table_name": "LocoWheelRegister_LwrId_238014_238028",
            "sql": "SELECT * FROM LocoWheelRegister_LwrId_238014_238028",
            "source_note": "partition clone probe (15 rows, subset of LocoWheelRegister)",
            "out": "loco_wheel_register_partition_LwrId_238014_238028.parquet",
            "cohort": False,
        },
        {
            "name": "WheelSetMeasurements_wsmWRId_238014_238028",
            "table_name": "WheelSetMeasurements_wsmWRId_238014_238028",
            "sql": "SELECT * FROM WheelSetMeasurements_wsmWRId_238014_238028",
            "source_note": "partition clone probe (90 rows, subset of WheelSetMeasurements)",
            "out": "wheel_measurements_partition_wsmWRId_238014_238028.parquet",
            "cohort": False,
        },
        {
            "name": "WheelReadingPurpose",
            "table_name": "WheelReadingPurpose",
            "sql_file": "wheel_reading_purpose.sql",
            "out": "wheel_reading_purpose.parquet",
            "cohort": False,
        },
        {
            "name": "WheelProfile",
            "table_name": "WheelProfile",
            "sql_file": "wheel_profile.sql",
            "out": "wheel_profile.parquet",
            "cohort": False,
        },
        {
            "name": "ScheduleTypes",
            "table_name": "ScheduleTypes",
            "sql_file": "schedule_types.sql",
            "out": "schedule_types.parquet",
            "cohort": False,
        },
        {
            "name": "Sections",
            "table_name": "Sections",
            "sql_file": "sections.sql",
            "out": "sections.parquet",
            "cohort": False,
        },
        {
            "name": "FunctionalLocations",
            "table_name": "FunctionalLocations",
            "sql_file": "functional_locations.sql",
            "out": "functional_locations.parquet",
            "cohort": False,
        },
        {
            "name": "Employees",
            "table_name": "Employees",
            "sql_file": "employees.sql",
            "out": "employees.parquet",
            "cohort": False,
        },
    ]
    extract(conn, targets, include_part=not args.no_part)


if __name__ == "__main__":
    main()