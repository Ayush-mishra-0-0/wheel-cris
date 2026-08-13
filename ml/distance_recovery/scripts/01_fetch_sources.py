"""Fetch the open sources for distance recovery.

Downloads (idempotent, cached in data/raw/):
  - station reference geojson (code -> lat/lon/state/zone)
  - rail network geojson (default: simplified VMAP network; --osm for the
    full OSM export from HDX)
  - timetable schedules (validation ground-truth distances)

Writes data/raw/sources_manifest.json with url, license note, sha256, bytes.

Usage:
  python scripts/01_fetch_sources.py [--osm] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from _net import download, get  # noqa: E402

CONFIG = json.loads((PROJECT_ROOT / "configs" / "sources.json").read_text(encoding="utf-8"))
RAW = PROJECT_ROOT / "data" / "raw"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", action="store_true", help="also fetch the full OSM rail export from HDX (91 MB)")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}

    for key in ("station_reference", "rail_network", "timetable_distances"):
        src = CONFIG[key]
        dest = RAW / src["file"]
        if args.force:
            dest.unlink(missing_ok=True)
        download(src["url"], dest)
        manifest[key] = {
            "name": src["name"], "url": src["url"], "license": src["license"],
            "caveats": src["caveats"], "bytes": dest.stat().st_size, "sha256": _sha256(dest),
        }
        print(f"[ok] {key:22s} {dest.name} ({dest.stat().st_size:,} bytes)")

    if args.osm:
        src = CONFIG["rail_network_osm"]
        dest = RAW / src["file"]
        if args.force:
            dest.unlink(missing_ok=True)
        download(src["url"], dest)
        # extract the geojson member for downstream use
        with zipfile.ZipFile(dest) as zf:
            zf.extract(src["zip_member"], RAW)
        member = RAW / src["zip_member"]
        manifest["rail_network_osm"] = {
            "name": src["name"], "url": src["url"], "license": src["license"],
            "caveats": src["caveats"], "bytes": dest.stat().st_size, "sha256": _sha256(dest),
            "zip_member": src["zip_member"], "extracted_bytes": member.stat().st_size,
        }
        print(f"[ok] rail_network_osm {dest.name} ({dest.stat().st_size:,} bytes)")

    (RAW / "sources_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest -> {RAW / 'sources_manifest.json'}")


if __name__ == "__main__":
    main()
