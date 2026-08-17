"""Env-driven dashboard configuration.

Everything the service needs from its environment, with sane local defaults.
No hard-coded addresses in the application code - set WHEEL_* to override.
"""
from __future__ import annotations

import os
from pathlib import Path

from ._paths import ML_ROOT


def _csv(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


# CORS: host SLAM app controls its own origins. Defaults to the local dev
# origins (vite) only; "*" is never the default so a production deployment
# must opt in explicitly via WHEEL_CORS_ORIGINS="*" or a real allow-list.
CORS_ORIGINS = _csv("WHEEL_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")

# Host/port used by the CLI launcher (uvicorn) - not the app itself.
HOST = os.environ.get("WHEEL_HOST", "127.0.0.1")
PORT = int(os.environ.get("WHEEL_PORT", "8033"))

# P1.1 fleet snapshot (one row per wheelset) feeding the fleet overview/risk
# endpoints. Env-overridable so tests / deployments can point at a fixture.
SNAPSHOT_PARQUET = Path(os.environ.get(
    "WHEEL_SNAPSHOT_PARQUET",
    str(ML_ROOT / "model_datasets" / "v5" / "fleet_snapshot.parquet"))).resolve()
SNAPSHOT_MANIFEST = SNAPSHOT_PARQUET.with_suffix(".manifest.json")

# Legacy bulk /loco/{n}/plots (matplotlib PNG/SVG per wheelset). The per-wheelset
# /wheelset/{id}/lifecycle/export contract supersedes it and the dashboard no
# longer calls it. Gated off by default: set WHEEL_ENABLE_LEGACY_PLOTS=1 to turn
# it back on (it loads the full WES frame on every request).
ENABLE_LEGACY_PLOTS = os.environ.get("WHEEL_ENABLE_LEGACY_PLOTS", "0") == "1"
