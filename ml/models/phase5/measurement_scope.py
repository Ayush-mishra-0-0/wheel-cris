"""Shared measurement-scope policy.

Trip-shed and other non-inspection measurements must not enter lifecycle
history or any future feature substrate.  The exact FunctionalLocations and
section codes are intentionally configuration, not a guessed model rule.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "measurement_scope_v1.json"


def _norm(value: object) -> str:
    return " ".join(str(value).strip().casefold().replace("_", " ").split())


def excluded_location_tokens() -> set[str]:
    tokens: set[str] = set()
    if CONFIG.exists():
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        tokens.update(_norm(x) for x in data.get("excluded_values", []))
        tokens.update(_norm(x) for x in data.get("functional_location_codes", []))
        tokens.update(_norm(x) for x in data.get("functional_location_names", []))
        tokens.update(_norm(x) for x in data.get("section_codes", []))
    extra = os.environ.get("WHEEL_EXCLUDED_LOCATION_CODES", "")
    tokens.update(_norm(x) for x in extra.split(",") if x.strip())
    return {x for x in tokens if x}


def inspection_scope_mask(frame: pd.DataFrame) -> pd.Series:
    """Return True for rows eligible for lifecycle/features.

    Matching is applied to any available location/section columns.  This lets
    the same policy work on WES today and on refreshed Bronze/Gold frames once
    FunctionalLocations and section codes are carried through.
    """
    tokens = excluded_location_tokens()
    mask = pd.Series(True, index=frame.index)
    if not tokens:
        return mask
    candidates = [
        c for c in (
            "home_shed", "shed_any", "shed_slam", "shed_fois", "station_fois",
            "functional_location", "functional_location_code", "FLocCode",
            "FLocName", "section", "section_code", "SecCode",
        ) if c in frame.columns
    ]
    if not candidates:
        return mask
    excluded = pd.Series(False, index=frame.index)
    for col in candidates:
        values = frame[col].map(_norm)
        excluded |= values.isin(tokens)
        # Keep a safe textual fallback for labels such as "Trip Shed" while
        # exact owner-approved codes are being registered.
        excluded |= values.str.replace(" ", "", regex=False).isin(
            {x.replace(" ", "") for x in tokens}
        )
    return ~excluded


def apply_inspection_scope(frame: pd.DataFrame) -> pd.DataFrame:
    """Filter a frame without changing its index or mutating the input."""
    return frame.loc[inspection_scope_mask(frame)].copy()
