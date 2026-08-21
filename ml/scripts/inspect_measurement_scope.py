"""Read-only audit of trip-shed keys and their WAP7 register usage."""
from __future__ import annotations

from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[1]


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def main() -> None:
    cfg = env()
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={cfg['DB_SERVER']};DATABASE={cfg['DB_NAME']};"
        f"UID={cfg['DB_USERNAME']};PWD={cfg['DB_PASSWORD']};"
        "TrustServerCertificate=yes;Encrypt=no",
        timeout=120,
    )
    queries = {
        "FLOC_TRIP": """
            SELECT FLocId,FLocName,FLocCode,FLocFuncLocationType
            FROM FunctionalLocations
            WHERE FLocName LIKE '%trip%' OR FLocCode LIKE '%trip%'
            ORDER BY FLocId
        """,
        "SECTION_TRIP": """
            SELECT SecId,SecCode,SecName,SecFuncLocation,SecType,SecKind
            FROM Sections
            WHERE SecName LIKE '%trip%' OR SecCode LIKE '%trip%'
            ORDER BY SecId
        """,
        "WAP7_FLOC_TRIP": """
            SELECT fl.FLocId,fl.FLocCode,fl.FLocName,COUNT_BIG(*) AS n
            FROM LocoWheelRegister l
            JOIN LocoMaster lm ON lm.LomId=l.LwrLocoId
            JOIN LocoTypes lt ON lt.LotId=lm.LomType
            JOIN FunctionalLocations fl ON fl.FLocId=l.LwrFuncLocId
            WHERE lt.LotTypeName='WAP7'
              AND (fl.FLocName LIKE '%trip%' OR fl.FLocCode LIKE '%trip%')
            GROUP BY fl.FLocId,fl.FLocCode,fl.FLocName
            ORDER BY n DESC
        """,
        "WAP7_SECTION_TRIP": """
            SELECT s.SecId,s.SecCode,s.SecName,COUNT_BIG(*) AS n
            FROM LocoWheelRegister l
            JOIN LocoMaster lm ON lm.LomId=l.LwrLocoId
            JOIN LocoTypes lt ON lt.LotId=lm.LomType
            JOIN Employees e ON TRY_CONVERT(bigint,l.LwrTakenBy)=e.EmpId
            JOIN Sections s ON s.SecId=e.EmpSection
            WHERE lt.LotTypeName='WAP7'
              AND (s.SecName LIKE '%trip%' OR s.SecCode LIKE '%trip%')
            GROUP BY s.SecId,s.SecCode,s.SecName
            ORDER BY n DESC
        """,
    }
    try:
        cur = conn.cursor()
        for name, query in queries.items():
            print(f"--- {name} ---")
            cur.execute(query)
            columns = [d[0] for d in cur.description]
            print(" | ".join(columns))
            for row in cur.fetchall():
                print(" | ".join(str(x) for x in row))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
