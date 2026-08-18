"""P1.1 - Fleet snapshot dataset builder.

Materialises a one-row-per-wheelset parquet of the CURRENT fleet state:

  - identity      : wheelset / loco number & id / shed / loco type / position
  - profile state : latest flange/root/thread/dia + days & km since turning
  - forecasts     : degradation 30/90/180d per dim (predicted level, delta)
                    + conformal low/high interval edges
  - P(turn)       : 30/60/90d probabilities (historical behaviour, separate)
  - limiting dim  : dia condemning (1016 mm hard stop) when reached within the
                    180d horizon, else the fastest-wearing flange/root/tread dim
  - risk signals  : KEPT SEPARATE (wear state, limit proximity, P(turn) are
                    distinct columns - never collapsed into one number)
  - provenance    : model_version / train_cutoff / data staleness so the UI can
                    show how old the snapshot and each wheelset's inputs are

Rebuild:
  ayush\\Scripts\\python -m dashboard.backend.build_fleet_snapshot
  # or: wheel-snapshot
Writes ml/model_datasets/v5/fleet_snapshot.parquet + .manifest.json

This is a point-in-time export for ranking/overview UI. It is NOT a serving
path - per-wheelset live forecasts still come from /api/v1/wheelset/... and
are always fresher than any snapshot.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # development
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ml"))  # ml

from dashboard.backend import service  # noqa: E402
from dashboard.backend._paths import ML_ROOT  # noqa: E402
from models.phase5.dashboard.backend.features import (  # noqa: E402
    extract_features, load_segments, load_wes,
)

ROOT = ML_ROOT
OUT = ROOT / "model_datasets" / "v5" / "fleet_snapshot.parquet"
MANIFEST = OUT.with_suffix(".manifest.json")

DEG_DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
WEAR_DIMS = ("wsmRoot", "wsmFlange", "wsmThread")
HORIZONS = (30, 90, 180)
CONDEMNING_DIA_MM = 1016.0
MAX_HORIZON = 180


def _crossing_days(times, values, limit: float, direction: str) -> float | None:
    """First day a piecewise-linear path crosses `limit`; None if never."""
    first = True
    prev_t = prev_v = None
    for t, v in zip(times, values):
        if v is None or not np.isfinite(v):
            first = True
            prev_t = prev_v = None
            continue
        if not first and prev_v is not None and prev_t is not None:
            lo_v, hi_v = sorted((prev_v, v))
            if lo_v <= limit <= hi_v and v != prev_v:
                if direction == "down":
                    return float(prev_t + (prev_v - limit) / (prev_v - v) * (t - prev_t))
                return float(prev_t + (limit - prev_v) / (v - prev_v) * (t - prev_t))
        first = False
        prev_t, prev_v = t, v
    return None


def _days_to_condemning(current: float | None, pred: dict) -> float | None:
    if current is None or not np.isfinite(current):
        return None
    if current <= CONDEMNING_DIA_MM:
        return 0.0
    return _crossing_days([0] + list(HORIZONS),
                          [current] + [pred.get(h) for h in HORIZONS],
                          CONDEMNING_DIA_MM, "down")


def build_snapshot() -> pd.DataFrame:
    wes_all = load_wes()
    seg = load_segments()
    svc = service.degradation_models()
    meta = service.degradation_meta()
    psvc = service.pturn_models()

    def feat_row(w: pd.DataFrame):
        anchor = pd.Timestamp(w.iloc[-1]["measurement_timestamp"])
        fr = extract_features(int(w.iloc[-1]["wheelset_equipment_id"]), anchor, w=w)
        return anchor, fr

    rows = []
    n_failed = 0
    t0 = time.time()
    groups = list(wes_all.groupby("wheelset_equipment_id", sort=False))
    for i, (ws_id, w) in enumerate(groups):
        anchor, fr = feat_row(w)
        if fr is None:
            n_failed += 1
            continue
        last = w.iloc[-1]
        cov = service.feature_coverage(fr, svc["num_feats"])

        # shed attribution lives on lifecycle_segments (seg), not WES
        shed_any = "NA"
        srow = seg[(seg["wheelset_equipment_id"] == ws_id) &
                   (seg["segment_index"] == int(last["seg_id"]))]
        if not srow.empty and pd.notna(srow.iloc[0]["shed_any"]):
            shed_any = str(srow.iloc[0]["shed_any"])

        row: dict = {
            "wheelset_equipment_id": int(ws_id),
            "locomotive_id": int(last["locomotive_id"]) if pd.notna(last["locomotive_id"]) else None,
            "loco_number": str(last["LomNumber"]) if pd.notna(last["LomNumber"]) else None,
            "loco_type": str(last["LocoType"]) if pd.notna(last["LocoType"]) else "NA",
            "home_shed": str(last["home_shed"]) if pd.notna(last["home_shed"]) else "NA",
            "shed_any": shed_any,
            "wheel_position_1_12": _f(last["wheel_position_1_12"]),
            "axle_position_1_6": _f(last["axle_position_1_6"]),
            "wheel_profile_2class": _f(last["wheel_profile_2class"]),
            "segment_index": int(last["seg_id"]) if pd.notna(last["seg_id"]) else None,
            "n_prior_turns": _f(last.get("seg_id")),
            "anchor": anchor,
            "latest_measurement": anchor,
            "days_since_turning": _f(last["days_since_turning"]),
            "distance_since_turning_km": _f(last["distance_since_turning_km"]),
            "feature_coverage": cov,
            "model_version": meta.get("model_version"),
            "train_cutoff": meta.get("train_cutoff"),
        }

        # degradation forecasts per dim x horizon (predicted level + delta + band).
        # Per-dim horizon models are reconciled into a monotone no-turn path
        # AFTER wheelset adaptation, so the snapshot can never show wear
        # decreasing / diameter increasing inside a segment.
        pred_by_dim: dict[str, dict[int, float | None]] = {}
        adapt = service.wheel_adaptation_at(int(ws_id), anchor)
        for dim in DEG_DIMS:
            current = fr.get(f"mean_{dim}")
            row[f"mean_{dim}"] = _f(current)
            levels: dict[int, float | None] = {}
            adapts: dict[int, dict] = {}
            raw = service._horizon_deltas(dim, fr)
            for h in HORIZONS:
                delta = raw.get(h)
                pred = current + delta if delta is not None and current is not None and np.isfinite(current) else None
                adj = adapt.get((dim, h)) if adapt else None
                if adj and adj["prior_n"] >= service.ADAPT_MIN_N and adj["bias"] is not None \
                        and not adj["boundary"] and service.adapt_applies(dim):
                    pred = pred + adj["bias"] if pred is not None else pred
                    adapts[h] = {"prior_n": adj["prior_n"], "bias_mm": adj["bias"], "applied": True}
                else:
                    adapts[h] = {"prior_n": adj["prior_n"] if adj else 0,
                                 "bias_mm": adj["bias"] if adj else None, "applied": False}
                levels[h] = pred
            if current is not None and np.isfinite(current):
                rawd = {h: (levels[h] - current) if levels[h] is not None else None
                        for h in HORIZONS}
                clamped = service._no_turn_monotone(dim, rawd)
                pred_by_dim[dim] = {h: (current + clamped.get(h))
                                    if clamped.get(h) is not None else None
                                    for h in HORIZONS}
            else:
                pred_by_dim[dim] = levels
            for h in HORIZONS:
                pred = pred_by_dim[dim][h]
                width = service._conformal_width_mm(dim, h)
                row[f"fc_{dim}_{h}d_pred"] = _f(pred)
                row[f"fc_{dim}_{h}d_delta"] = _f(pred - current) if pred is not None and current is not None and np.isfinite(current) else None
                row[f"fc_{dim}_{h}d_low"] = _f(pred - width) if pred is not None and width is not None else None
                row[f"fc_{dim}_{h}d_high"] = _f(pred + width) if pred is not None and width is not None else None
                row[f"fc_{dim}_{h}d_adapt_prior_n"] = adapts[h]["prior_n"]
                row[f"fc_{dim}_{h}d_adapt_bias"] = adapts[h]["bias_mm"]
                row[f"fc_{dim}_{h}d_adapt_applied"] = adapts[h]["applied"]
            row[f"{dim}_model_source"] = service.model_of_record().get(dim)

        # P(turn) - separate signal, never merged into wear risk
        Xp = service._feature_vector(fr, psvc["num_feats"], psvc["cat_feats"], psvc["enc"])
        for h in psvc["models"]:
            p = float(psvc["models"][h].predict_proba(Xp)[0, 1])
            row[f"pturn_{h}d"] = round(p, 4)

        # limiting dimension
        dttl = _days_to_condemning(fr.get("mean_wsmDia"), pred_by_dim["wsmDia"])
        row["days_to_condemning_dia"] = round(dttl, 1) if dttl is not None else None
        if dttl is not None and dttl <= MAX_HORIZON:
            row["limiting_dim"] = "wsmDia"
            row["limiting_reason"] = "dia reaches condemning hard stop (1016 mm) within horizon"
        else:
            # fastest-wearing primary wear dim (90d change in mm)
            rates = {}
            for dim in WEAR_DIMS:
                d90 = pred_by_dim[dim].get(90)
                cur = fr.get(f"mean_{dim}")
                if d90 is not None and cur is not None and np.isfinite(d90) and np.isfinite(cur):
                    rates[dim] = d90 - cur
            if rates:
                top = max(rates, key=rates.get)
                row["limiting_dim"] = top
                row["limiting_reason"] = "fastest 90d wear among flange/root/tread (no approved action limit)"
            else:
                row["limiting_dim"] = None
                row["limiting_reason"] = None

        rows.append(row)
        if (i + 1) % 2500 == 0:
            print(f"  {i+1}/{len(groups)} wheelsets ({time.time()-t0:.0f}s)")

    df = pd.DataFrame(rows)
    df["staleness_days"] = (pd.Timestamp.now() - pd.to_datetime(df["latest_measurement"])).dt.days
    print(f"built {len(df)} rows, {n_failed} wheelsets skipped (no feature row), {time.time()-t0:.0f}s")
    return df


def write(df: pd.DataFrame) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    srcs = [
        ML_ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet",
        ML_ROOT / "model_datasets" / "v2" / "exposure_features_v2.parquet",
        ML_ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet",
    ]
    manifest = {
        "task": "fleet snapshot (P1.1) - one row per wheelset, current state",
        "contract": "fleet_snapshot_v1",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_wheelsets": int(len(df)),
        "n_with_forecast": int(df["model_version"].notna().sum()),
        "model_version": str(df["model_version"].dropna().iloc[0]) if "model_version" in df and df["model_version"].notna().any() else None,
        "train_cutoff": str(df["train_cutoff"].dropna().iloc[0]) if "train_cutoff" in df and df["train_cutoff"].notna().any() else None,
        "model_of_record": service.degradation_meta().get("model_of_record"),
        "sources": [{"path": str(p.relative_to(ML_ROOT)), "sha256": _sha(p)} for p in srcs if p.exists()],
        "rebuild": "ayush\\Scripts\\python -m dashboard.backend.build_fleet_snapshot",
        "note": ("Point-in-time export for ranking/overview. P(turn), wear state and "
                 "limit proximity are separate columns and must not be collapsed. "
                 "Live per-wheelset forecasts come from the API, not this file."),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT.relative_to(ML_ROOT))


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _f(v) -> float | None:
    try:
        x = float(v)
        return None if np.isnan(x) else round(x, 4)
    except (TypeError, ValueError):
        return None


def main() -> None:
    t0 = time.time()
    print("building fleet snapshot...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = build_snapshot()
    write(df)
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
