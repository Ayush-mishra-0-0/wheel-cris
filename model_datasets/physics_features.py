"""Physics-informed feature engineering — V1.1 (existing data only, no new sources).

Computes a per-measurement "physics state" table from the raw WheelSetMeasurements
frame. Every feature is computed AS-OF the measurement timestamp (point-in-time
safe by construction): only data up to and including that measurement is used, so
a row joined on `interval_end_measurement_id` never leaks the future label.

Feature families:
  - Level 1 (physics constraints)
      phys_remaining_material_mm_s1/s2  : current dia - condemning dia
      phys_wear_fraction_s1/s2          : (current - condemning)/(initial - condemning)
      phys_material_consumed_pct_s1/s2  : 1 - wear_fraction (fraction of usable material used)
      phys_initial_dia_mm_s1/s2         : as-delivered (provisioned) or first-observed diameter
  - Level 2 (physics-inspired trends)
      phys_cumulative_wear_mm_s1/s2     : initial - current (total material removed so far)
      phys_interval_wear_rate_s1/s2     : own-interval delta/days (known at interval end)
      phys_wear_acceleration_s1/s2      : change in interval wear rate vs previous interval
      phys_ema_wear_rate_s1/s2          : halflife-3 EWMA of interval wear rates
      phys_remaining_budget_days_s1/s2  : remaining material / |ema wear rate|
  - Maintenance / life-cycle state
      phys_turning_events_cumulative    : number of turning events so far
      phys_wheelset_age_days            : days since first observed measurement
      (days_since_turning already exists in the feature store; not duplicated)
  - Raw measured geometry at interval end (geom_*)
      Absolute wheel measurements as known to the maintenance engineer at the
      prediction timestamp (current diameter/root/flange/tread/tire thickness,
      wear + wear rate). These are the highest-signal features (|corr| up to
      ~0.73) and were missing from v1.0, which only carried interval deltas.
      NA outside the quarantine window is imputed downstream.

Constants (engineering inputs, provided by domain owner):
  - CONDEMNING_DIA_MM = 1016.0  (lower diameter limit)
  - NEW_DIA_MM = 1096.0         (upper diameter limit / as-new)
  - DIA_PLAUSIBLE = [1016.0, 1096.0]  (physical operating range; sentinels outside are quarantined)
  - EMA_HALFLIFE = 3 intervals
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from silver_gold.transform import BRONZE_DIR, _sha256  # noqa: E402

MEASUREMENTS_PATH = BRONZE_DIR / "wheel_measurements.parquet"
OUT_DIR = PROJECT_ROOT / "model_datasets" / "physics"
PHYSICS_VERSION = "v1.1"

CONDEMNING_DIA_MM = 1016.0
NEW_DIA_MM = 1096.0
DIA_PLAUSIBLE = (1016.0, 1096.0)
EMA_HALFLIFE = 3

# Raw measured geometry at the measurement timestamp (point-in-time safe: this IS
# the state a maintenance engineer holds when predicting the next interval).
# Quarantine windows from observed plausible ranges (see audit in notebook).
GEOMETRY_COLUMNS = {
    "wsmDia1": (1016.0, 1096.0),
    "wsmDia2": (1016.0, 1096.0),
    "wsmRoot1": (0.0, 50.0),
    "wsmRoot2": (0.0, 50.0),
    "wsmFlange1": (0.0, 40.0),
    "wsmFlange2": (0.0, 40.0),
    "wsmFlangeThickness1": (10.0, 45.0),
    "wsmFlangeThickness2": (10.0, 45.0),
    "wsmWear": (-60.0, 60.0),
    "wsmWear2": (-60.0, 60.0),
    "wsmWearRate": (-20.0, 20.0),
    "wsmWearRate2": (-20.0, 20.0),
    "wsmTireThikness1": (20.0, 80.0),
    "wsmTireThikness2": (20.0, 80.0),
    "wsmThread1": (0.0, 10.0),
    "wsmThread2": (0.0, 10.0),
    "wsmKvalue1": (0.0, 400.0),
    "wsmSDistance1": (0.0, 200.0),
}
GEOMETRY_PREFIX = "geom_"


def _fingerprint(*items: str) -> str:
    digest = hashlib.sha256()
    for item in items:
        digest.update(item.encode("utf-8"))
    return digest.hexdigest()[:16]


def _load_measurements() -> pd.DataFrame:
    cols = [
        "wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmProvDate",
        "wsmDia1", "wsmDia2", "wsmProvDia1", "wsmProvDia2", "wsmturning1",
    ]
    cols = list(dict.fromkeys(cols + list(GEOMETRY_COLUMNS)))
    frame = pd.read_parquet(MEASUREMENTS_PATH, columns=cols).copy()
    frame["wsmId"] = pd.to_numeric(frame["wsmId"], errors="coerce").astype("Int64")
    frame["wheelset_equipment_id"] = pd.to_numeric(frame["wsmEquipmentId"], errors="coerce").astype("Int64")
    frame["wsmturning1"] = pd.to_numeric(frame["wsmturning1"], errors="coerce")
    for col in ("wsmDia1", "wsmDia2", "wsmProvDia1", "wsmProvDia2", *GEOMETRY_COLUMNS):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    for col in ("wsmUpdatedOn", "wsmProvDate"):
        frame[col] = pd.to_datetime(frame[col], errors="coerce")
    frame = frame.dropna(subset=["wheelset_equipment_id", "wsmUpdatedOn"])
    # Quarantine implausible diameters (sentinels up to ~1e6 mm) to NA; physics
    # state for those rows becomes partially missing and is imputed downstream.
    for col in ("wsmDia1", "wsmDia2"):
        frame.loc[~frame[col].between(*DIA_PLAUSIBLE, inclusive="neither"), col] = np.nan
    return frame.sort_values(["wheelset_equipment_id", "wsmUpdatedOn"]).reset_index(drop=True)


def _quarantine(value: pd.Series) -> pd.Series:
    return value.where(value.between(*DIA_PLAUSIBLE, inclusive="neither"))


def _side_state(df: pd.DataFrame, dia_col: str, prov_col: str, suffix: str) -> pd.DataFrame:
    """Compute per-side Level 1 + Level 2 physics state (point-in-time safe)."""
    g = df.groupby("wheelset_equipment_id", sort=False)
    max_dia = df.groupby("wheelset_equipment_id")[dia_col].transform("max")
    prov_ok = df[prov_col].where(df[prov_col].between(*DIA_PLAUSIBLE, inclusive="neither")).notna()
    initial = pd.Series(np.where(prov_ok, df[prov_col], np.nan), index=df.index)
    initial = initial.fillna(max_dia).groupby(df["wheelset_equipment_id"]).transform("max")

    prev_dia = g[dia_col].shift(1)
    prev_time = g["wsmUpdatedOn"].shift(1)
    interval_days = (df["wsmUpdatedOn"] - prev_time).dt.days
    delta = df[dia_col] - prev_dia
    wear_rate = (delta / interval_days).where(interval_days > 0).replace([np.inf, -np.inf], np.nan)
    ema_rate = wear_rate.groupby(df["wheelset_equipment_id"]).transform(lambda s: s.ewm(halflife=EMA_HALFLIFE, min_periods=1).mean())
    wear_accel = wear_rate - wear_rate.groupby(df["wheelset_equipment_id"]).shift(1)

    current = df[dia_col]
    remaining = current - CONDEMNING_DIA_MM
    usable = initial - CONDEMNING_DIA_MM
    wear_frac = (remaining / usable).clip(0.0, 1.0)

    out = pd.DataFrame({
        f"phys_initial_dia_mm_{suffix}": initial,
        f"phys_remaining_material_mm_{suffix}": remaining,
        f"phys_wear_fraction_{suffix}": wear_frac,
        f"phys_material_consumed_pct_{suffix}": 1.0 - wear_frac,
        f"phys_cumulative_wear_mm_{suffix}": initial - current,
        f"phys_interval_wear_rate_{suffix}": wear_rate,
        f"phys_wear_acceleration_{suffix}": wear_accel,
        f"phys_ema_wear_rate_{suffix}": ema_rate,
        f"phys_remaining_budget_days_{suffix}": (remaining / ema_rate.abs().clip(lower=0.005)).clip(-8000, 8000),
    })
    for col in out.columns:
        out[col] = out[col].replace([np.inf, -np.inf], np.nan)
    return out


def _physics_state(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("wheelset_equipment_id", sort=False)

    # --- Level 1 + Level 2 per side (real wsmDia1 / wsmDia2) ------------------
    side1 = _side_state(df, "wsmDia1", "wsmProvDia1", "s1")
    side2 = _side_state(df, "wsmDia2", "wsmProvDia2", "s2")

    # --- Maintenance / life-cycle state -----------------------------------
    turning_events = g["wsmturning1"].apply(lambda s: s.fillna(0).cumsum())
    turning_events = turning_events.to_numpy()
    turning_events = pd.Series(turning_events, index=df.index)

    wheelset_age_days = (df["wsmUpdatedOn"] - df.groupby("wheelset_equipment_id")["wsmUpdatedOn"].transform("min")).dt.days

    out = pd.concat([side1, side2], axis=1)
    out["phys_turning_events_cumulative"] = turning_events
    out["phys_wheelset_age_days"] = wheelset_age_days

    # Raw measured geometry at this measurement (absolute state at prediction
    # time — point-in-time safe by construction; NA outside quarantine window).
    for raw_col, (lo, hi) in GEOMETRY_COLUMNS.items():
        out[f"{GEOMETRY_PREFIX}{raw_col}"] = df[raw_col].where(df[raw_col].between(lo, hi, inclusive="neither"))

    out.insert(0, "wsmId", df["wsmId"].to_numpy())
    out.insert(1, "wheelset_equipment_id", df["wheelset_equipment_id"].to_numpy())
    out.insert(2, "measurement_timestamp", df["wsmUpdatedOn"].to_numpy())
    return out


def build_physics_features(force: bool = False) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = OUT_DIR / "physics_features_v1.1.parquet"
    if parquet_path.exists() and not force:
        raise FileExistsError(f"{parquet_path} exists; use --force to regenerate")

    measurements = _load_measurements()
    state = _physics_state(measurements)
    state = state.dropna(subset=["wsmId"])

    manifest = {
        "physics_version": PHYSICS_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {"wheel_measurements": _sha256(MEASUREMENTS_PATH)},
        "fingerprint": _fingerprint(str(_sha256(MEASUREMENTS_PATH)), PHYSICS_VERSION),
        "rows": int(len(state)),
        "wheelsets": int(state["wheelset_equipment_id"].nunique()),
        "columns": [c for c in state.columns],
        "geometry_columns": {k: list(v) for k, v in GEOMETRY_COLUMNS.items()},
        "constants": {
            "condemning_dia_mm": CONDEMNING_DIA_MM,
            "dia_plausible": list(DIA_PLAUSIBLE),
            "ema_halflife": EMA_HALFLIFE,
        },
        "note": "Engineering assumptions (condemning dia, plausible window) are NOT approved; see docs/degradation_semantics.md.",
    }

    state.to_parquet(parquet_path, index=False)
    manifest_path = OUT_DIR / "physics_features_manifest_v1.1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"physics features: {state.shape} -> {parquet_path.relative_to(PROJECT_ROOT)}")
    return {"physics_features": parquet_path, "manifest": manifest_path}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, path in build_physics_features(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
