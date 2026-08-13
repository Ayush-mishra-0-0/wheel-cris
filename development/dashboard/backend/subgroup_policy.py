"""Subgroup confidence policy for serving forecast responses.

Layer 2 policy encoding of `models/experiments/v5/subgroup_stability.json`
collapse rows. A wheelset's forecast for a (dim, horizon) is downgraded to
"reduced confidence" when the wheelset belongs to a collapsed subgroup for that
dimension. Groups covered:

  - shed           : shed_any attribution (feature row)
  - profile_class  : wheel_profile_2class
  - wheel_position : wheel_position_1_12
  - axle           : axle_position_1_6
  - age_cohort     : wheel_age_days_proxy quartile band
  - wear_quantile  : current value of the dim, test quartile band

Levels in the artefact are the subgroup label strings (e.g. "PADX", "1.0",
"2080.0, 8116.0"). This module translates a feature row into the subset of
collapse rows that apply, so the API can attach `subgroup_flags` to each
forecast without retraining or touching the model.

Policy rule (matches the artefact): a group collapses when n<100, coverage<0.70,
or |bias| > 2x the dimension noise floor. Over-coverage is conservative and not
flagged.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SUBGROUP_ARTEFACT = ROOT / "ml" / "models" / "experiments" / "v5" / "subgroup_stability.json"

NUMERIC_GROUP_KEYS = ("profile_class", "wheel_position", "axle")


@lru_cache(maxsize=1)
def collapse_index() -> dict:
    """Return {(dim, horizon): [collapse rows]} from the subgroup artefact."""
    if not SUBGROUP_ARTEFACT.exists():
        return {}
    arte = json.loads(SUBGROUP_ARTEFACT.read_text())
    index: dict = {}
    for row in arte.get("collapse_groups", []):
        index.setdefault((row["dim"], row["horizon"]), []).append(row)
    return index


def _band_contains(level: str, value: float | None) -> bool:
    """True when `value` falls inside a quartile band label like '2080.0, 8116.0'."""
    if value is None or not np.isfinite(value):
        return False
    try:
        lo_s, hi_s = level.split(",")
        return float(lo_s) <= value <= float(hi_s)
    except (ValueError, AttributeError):
        return False


def _numeric_level_matches(level: str, value: float | None) -> bool:
    """Categorical numeric subgroup level (e.g. '1.0', '5.0', '3')."""
    if value is None or not np.isfinite(value):
        return False
    for cand in (f"{value:.1f}", str(int(value))):
        if cand == level:
            return True
    return False


def subgroup_flags(feat: dict, dim: str, horizon: int) -> list[dict]:
    """Collapse rows that apply to `feat` for this (dim, horizon), if any."""
    index = collapse_index()
    rows = index.get((dim, horizon), [])
    flags: list[dict] = []
    for row in rows:
        group = row["group"]
        level = row["level"]
        hit = False
        if group == "shed":
            hit = str(feat.get("shed_any", "")).strip() == level
        elif group == "profile_class":
            hit = _numeric_level_matches(level, feat.get("wheel_profile_2class"))
        elif group == "wheel_position":
            hit = _numeric_level_matches(level, feat.get("wheel_position_1_12"))
        elif group == "axle":
            hit = _numeric_level_matches(level, feat.get("axle_position_1_6"))
        elif group == "age_cohort":
            hit = _band_contains(level, feat.get("wheel_age_days_proxy"))
        elif group == "wear_quantile":
            hit = _band_contains(level, feat.get(f"mean_{dim}"))
        if hit:
            flags.append({
                "group": group, "level": level,
                "reason": row["reason"],
                "n": row["n"],
                "bias_mm": row["bias_mm"],
                "coverage": row["coverage"],
                "noise_floor_mm": row["noise_floor_mm"],
            })
    return flags
