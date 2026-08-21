"""Versioned WES artifact selection for rebuilds and serving."""
from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WES_DIR = ROOT / "model_datasets" / "v3"
FROZEN_WES = WES_DIR / "wheel_engineering_state_v1.0.parquet"
CURRENT_WES = WES_DIR / "wheel_engineering_state_v1.1.parquet"


def current_wes_path() -> Path:
    """Return explicit override, refreshed WES, or the frozen fallback."""
    override = os.environ.get("WHEEL_WES_PARQUET")
    if override:
        path = Path(override)
        if not path.is_absolute():
            path = ROOT / path
        return path
    return CURRENT_WES if CURRENT_WES.exists() else FROZEN_WES
