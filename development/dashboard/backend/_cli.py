"""Console entry points for the Wheel Lifecycle dashboard.

Launched via the `wheel-dashboard` console script after `pip install -e .`
(a single command, no PYTHONPATH fiddling). _paths.py already injects the
`ml` root so `models.*` is importable from within the dashboard backend.
"""
from __future__ import annotations

import os

from ._paths import ML_ROOT  # noqa: F401  (ensures sys.path has the ml root)


def serve() -> None:
    """Run the FastAPI app with env-driven host/port."""
    import uvicorn

    cfg = os.environ.get("WHEEL_DASHBOARD_CONFIG", "development")
    host = os.environ.get("WHEEL_HOST", "127.0.0.1")
    port = int(os.environ.get("WHEEL_PORT", "8033"))
    reload = os.environ.get("WHEEL_RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run("dashboard.backend.main:app", host=host, port=port, reload=reload)