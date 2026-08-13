"""Resolve the ML root and make it importable for the dashboard backend.

The product code lives under development/dashboard/backend/ but reads serving
models, feature extractors and datasets from the ml/ tree. This module inserts
the ml root on sys.path and exposes ML_ROOT so sibling modules compute their
own artifact paths without hard-coding absolute locations.
"""
from __future__ import annotations

import sys
from pathlib import Path

# development/dashboard/backend/_paths.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
ML_ROOT = REPO_ROOT / "ml"

# Make `models.phase5.dashboard.backend.features` (== ml/.../features.py) importable.
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))
