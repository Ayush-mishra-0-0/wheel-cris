"""Layer 5 dashboard - service layer (models + feature extraction).
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from ._paths import ML_ROOT
from .config import SNAPSHOT_MANIFEST, SNAPSHOT_PARQUET
from models.phase5.dashboard.backend.features import (
    extract_features, latest_anchor, load_segments, load_wes,
)
from .subgroup_policy import subgroup_flags

ROOT = ML_ROOT
DEG_DIR = ROOT / "models" / "phase5" / "serving" / "degradation"
RATE_DIR = ROOT / "models" / "phase5" / "serving" / "degradation_rate"
PTURN_DIR = ROOT / "models" / "phase5" / "serving" / "turn_probability"
PTURN_BENCH = ROOT / "models" / "experiments" / "v5" / "turn_probability_benchmark.json"
V4_TURN_ATTRIB = ROOT / "models" / "experiments" / "v4" / "wheel_attribution_turn.parquet"
V4_ROOT_ATTRIB = ROOT / "models" / "experiments" / "v4" / "wheel_attribution_root.parquet"
SEG = ROOT / "model_datasets" / "v5" / "lifecycle_segments_shed.parquet"
TURNS = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
TRAJ_ARTEFACT = ROOT / "models" / "experiments" / "v5" / "trajectory_product_analysis.json"
FLEET_BACKTEST = ROOT / "models" / "experiments" / "v5" / "fleet_backtest.json"
ADAPT_ARTEFACT = ROOT / "model_datasets" / "v5" / "wheelset_adaptation.parquet"

HORIZONS = (30, 90, 180)
DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
WEAR_DIMS = ("wsmRoot", "wsmFlange", "wsmThread")
# Implausibility flags (re-derived 2026-08-17 from the same-day measurement
# repeatability floor: dia MAD 1.5mm, root ~0.2mm, flange ~0.11mm). Tolerances
# sit just above the noise floor so prediction noise does not fire the flags;
# the pre-fix values (0.05 / 0.001 mm) were below the noise floor and flagged
# improvement/increase on nearly every wheelset.
WEAR_BETTER_TOL = 0.25      # mm threshold below current to flag "wear improves"
DIA_INC_TOL = 1.5           # mm; predicted diameter above current
DAY = np.timedelta64(1, "D")

# Wear-margin watch bands (DISPLAY-only, never a sorting/condemning key; the
# approved Wrpld limits in LIMIT_REGISTER stay authoritative). `band` describes
# how close the wear value sits to its approved limit relative to the limit's
# range: healthy >= 35% headroom, watch < 35% headroom, near < 15% headroom.
WATCH_BAND_HEALTHY = 0.35
WATCH_BAND_NEAR = 0.15

# ---------------------------------------------------------------------------
# Second-stage wheelset adaptation (empirical-Bayes residual shrinkage).
# At an anchor with prior_n >= 2 same-segment residuals, the population
# forecast is shifted by bias_shrunk = mean(residual) * n/(n+K). Only rows
# before the anchor in the SAME segment are used (built by
# build_wheelset_adaptation.py); turn/replacement boundaries have no
# same-segment history and are never adapted.
# ---------------------------------------------------------------------------
ADAPT_K = 3.0
ADAPT_MAX_PRIOR = 5
ADAPT_MIN_N = 2

# ---------------------------------------------------------------------------
# Deterministic TURN/RESET operator (Lever 1) - maintenance policy, NOT ML.
# A restored state is only claimed when the anchor's own lifecycle row is a
# post-turn/replacement boundary (same event rule as build_lifecycle_segments:
# dia cut >= TURN_CUT_MIN with a flange-or-root restore, or a replacement).
# This lets the renderer CONTINUE THE PLOT from the restored level instead of
# extrapolating the reset as continuous wear.
# ---------------------------------------------------------------------------
TURN_CUT_MIN = 1.0
WEAR_RESTORE_MM = 0.2

# ---------------------------------------------------------------------------
# Engineering limit register (MAINTENANCE POLICY, not ML).
# The Wrpld table is the authoritative wear register (configs/limit_register_v1.json,
# ratified 2026-08-19): flange 0-3 mm, root 0-6 mm, tread 0-6.5 mm (max = condemning,
# lower is better) + dia 1016 mm dead floor. All four are APPROVED and drive
# time-to-limit and the limiting dimension. The three-step ACTION ladder
# (attention / plan turn / turn now) remains open with C&W / standards; those are
# separate thoughts and are NOT required for condemning-limit proximity.
# Every threshold MUST be registered here as a versioned constant (with status),
# never hardcoded in request code. `status` is surfaced via /api/v1/config so the
# UI can label approved vs provisional vs pending.
# Direction: "down" = value falls toward the limit (dia); "up" = value rises toward
# the limit (wear dims: flange/root/tread grow toward condemning).
# ---------------------------------------------------------------------------
CONDEMNING_DIA_MM = 1016.0
LIMIT_REGISTER = {
    "wsmDia": {
        "limit_mm": CONDEMNING_DIA_MM,
        "direction": "down",
        "label": "condemning (dia)",
        "unit": "mm",
        "status": "approved",
        "owner": "maintenance policy (RDSO/shed)",
        "note": "Hard stop: wheel diameter must not fall below 1016 mm.",
    },
    "wsmFlange": {
        "limit_mm": 3.0,
        "direction": "up",
        "label": "condemning (flange wear)",
        "unit": "mm",
        "status": "approved",
        "owner": "Wrpld (authoritative wear register)",
        "note": "Wrpld: flange wear range 0-3 mm; 3.0 mm = condemning, lower is better.",
    },
    "wsmRoot": {
        "limit_mm": 6.0,
        "direction": "up",
        "label": "condemning (root wear)",
        "unit": "mm",
        "status": "approved",
        "owner": "Wrpld (authoritative wear register)",
        "note": ("Wrpld: root wear range 0-6 mm; 6.0 mm = condemning, lower is better. "
                 "Supersedes any earlier 3 mm root figure."),
    },
    "wsmThread": {
        "limit_mm": 6.5,
        "direction": "up",
        "label": "condemning (tread wear)",
        "unit": "mm",
        "status": "approved",
        "owner": "Wrpld (authoritative wear register)",
        "note": "Wrpld: tread wear range 0-6.5 mm; 6.5 mm = condemning, lower is better.",
    },
}
TTL_HORIZONS = (30, 90, 180)


def limits_register() -> dict:
    """Copy of LIMIT_REGISTER for the /config surface (approved vs provisional)."""
    return {dim: dict(reg) for dim, reg in LIMIT_REGISTER.items()}


@lru_cache(maxsize=1)
def degradation_models() -> dict:
    feats = json.loads((DEG_DIR / "features.json").read_text())
    enc = joblib.load(DEG_DIR / "encoder.joblib")
    models = {}
    for dim in DIMM:
        for h in HORIZONS:
            models[(dim, h)] = joblib.load(DEG_DIR / f"model_{dim}_{h}d.joblib")
    return {"models": models, "enc": enc, "num_feats": feats["num_feats"],
            "cat_feats": feats["cat_feats"]}


@lru_cache(maxsize=1)
def degradation_rate_models() -> dict:
    """Option-3 wear-rate head (rate + integrate). One XGB per dim predicting
    mm/day from the DENSE adjacent same-segment pairs; 30/90/180 d values are
    the integrated delta = decay_k * rate * horizon. Backup to the per-horizon
    head lives in DEG_DIR and is always available if the rate dir is absent."""
    feats = json.loads((RATE_DIR / "features.json").read_text())
    enc = joblib.load(RATE_DIR / "encoder.joblib")
    models = {dim: joblib.load(RATE_DIR / f"model_{dim}.joblib") for dim in DIMM}
    return {"models": models, "enc": enc, "num_feats": feats["num_feats"],
            "cat_feats": feats["cat_feats"]}


@lru_cache(maxsize=1)
def rate_champion() -> dict:
    """Champion/backup contract for the degradation service.

    Written by train_wear_rate_models.py from the frozen v5 TEST benchmark:
    `dim_model_of_record` picks, PER DIMENSION, the head with the lower mean
    served no-turn level-MAE across 30/90/180 d. Missing/broken artifact falls
    back to the per-horizon head for every dim (backup requirement).
    """
    p = RATE_DIR / "champion.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def model_of_record() -> dict:
    """{dim: 'wear_rate' | 'per_horizon_xgb'} for the degradation service."""
    champ = rate_champion()
    choice = champ.get("dim_model_of_record", {})
    if not isinstance(choice, dict) or not RATE_DIR.exists():
        return {dim: "per_horizon_xgb" for dim in DIMM}
    return {dim: (choice.get(dim, "per_horizon_xgb")
                  if isinstance(choice.get(dim), str) else "per_horizon_xgb")
            for dim in DIMM}


def adapt_applies(dim: str) -> bool:
    """Whether second-stage wheelset adaptation applies to `dim`.

    The adaptation artifact (wheelset_adaptation.parquet) is built from the
    PER-HORIZON head's residuals (build_wheelset_adaptation.py). For dims the
    champion routes to the wear-rate head those residual biases are stale and
    can inject non-physical decreasing wear - the rate head is already horizon-
    calibrated, so adaptation is skipped for it (documented divergence).
    """
    return model_of_record().get(dim, "per_horizon_xgb") == "per_horizon_xgb"


def _horizon_deltas(dim: str, fr: dict | None) -> dict[int, float | None]:
    """Raw (pre-adaptation, pre-monotone) per-horizon deltas for `dim`.

    Model of record per dimension (champion.json). The wear-rate head
    integrates delta_H = decay_k(dim,H) * rate * H with the rate sign-clamped
    to physical direction (wear >= 0, dia <= 0); the per-horizon head predicts
    each horizon delta independently (the two can disagree - that is exactly
    what the monotone no-turn path reconciles afterwards in serving).
    """
    if fr is None:
        return {h: None for h in HORIZONS}
    if model_of_record()[dim] == "wear_rate":
        try:
            svc = degradation_rate_models()
            champ = rate_champion()
        except Exception:
            svc = None
            champ = {}
        if svc is not None:
            X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
            rate = float(svc["models"][dim].predict(X)[0])
            if not np.isfinite(rate):
                return {h: None for h in HORIZONS}
            if dim == "wsmDia":
                rate = min(rate, 0.0)
            else:
                rate = max(rate, 0.0)
            kk = champ.get("decay_k", {})
            return {h: (float(kk.get(f"{dim}_{h}d", 1.0)) * rate * h)
                    for h in HORIZONS}
    svc = degradation_models()
    X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
    return {h: float(svc["models"][(dim, h)].predict(X)[0]) for h in HORIZONS}


@lru_cache(maxsize=1)
def pturn_models() -> dict:
    feats = json.loads((PTURN_DIR / "features.json").read_text())
    enc = joblib.load(PTURN_DIR / "encoder.joblib")
    models = {h: joblib.load(PTURN_DIR / f"model_{h}d.joblib") for h in feats["horizons"]}
    manifest = json.loads((PTURN_DIR / "manifest.json").read_text())
    rate = {m["horizon"]: m["turn_rate_train"] for m in manifest["models"]}
    return {"models": models, "enc": enc, "num_feats": feats["num_feats"],
            "cat_feats": feats["cat_feats"], "turn_rate_train": rate}


@lru_cache(maxsize=1)
def wheelset_adaptation() -> dict | None:
    """Load the wheelset-adaptation stream (second-stage residual shrinkage).

    Returns {wheelset_equipment_id: {
        "ts": np.ndarray (ns int64, sorted),
        "rows": list[dict] aligned to ts, each {(dim, h): {
            "prior_n": int, "bias": float | None, "boundary": bool}}}.
    bias is the empirical-Bayes shrunk residual offset computed only from prior
    same-segment rows; None when prior_n < ADAPT_MIN_N. Lookup is AS-OF: the
    latest substrate row at or before the anchor (its bias already reflects all
    observed outcomes known at that point).
    """
    if not ADAPT_ARTEFACT.exists():
        return None
    a = pd.read_parquet(ADAPT_ARTEFACT)
    ts_ns = a["measurement_timestamp"].to_numpy(dtype="datetime64[ns]").astype("int64")
    out: dict[int, dict] = {}
    for idx, row in a.iterrows():
        ws = int(row["wheelset_equipment_id"])
        entry = out.setdefault(ws, {"ts": [], "rows": []})
        entry["ts"].append(int(ts_ns[idx]))
        d = {}
        for dim in DIMM:
            for h in HORIZONS:
                tag = f"{dim}_{h}d"
                n = int(row[f"n_{tag}"])
                b = row[f"bias_{tag}"]
                d[(dim, h)] = {
                    "prior_n": n,
                    "bias": float(b) if n >= ADAPT_MIN_N and np.isfinite(b) else None,
                    "boundary": bool(row["is_boundary"]),
                }
        entry["rows"].append(d)
    for entry in out.values():
        entry["ts"] = np.asarray(entry["ts"], dtype="int64")
    return out


def wheel_adaptation_at(ws: int, anchor: pd.Timestamp) -> dict | None:
    """As-of lookup of the adaptation stream for one anchor.

    Returns the {(dim, h): ...} block of the latest substrate row at or before
    the anchor, or None if the wheelset is absent / the stream is unavailable.
    """
    ad = wheelset_adaptation()
    if not ad:
        return None
    entry = ad.get(int(ws))
    if not entry:
        return None
    t_ns = int(pd.Timestamp(anchor).value)
    pos = int(np.searchsorted(entry["ts"], t_ns, side="right")) - 1
    if pos < 0:
        return None
    return entry["rows"][pos]


@lru_cache(maxsize=1)
def pturn_reliability() -> dict:
    """Fleet-backtest ROC-AUC per P(turn) horizon (C1 XGB), for uncertainty context."""
    if not FLEET_BACKTEST.exists():
        return {}
    try:
        data = json.loads(FLEET_BACKTEST.read_text())
        horizons = data.get("turn_probability", {}).get("horizons", {})
        out = {}
        for h, block in horizons.items():
            models = block.get("models", {})
            if "C1_xgb" in models:
                out[int(h)] = {"roc_auc": models["C1_xgb"].get("roc_auc"),
                               "turn_rate_test": models["C1_xgb"].get("turn_rate_test")}
        return out
    except (KeyError, TypeError, ValueError):
        return {}


@lru_cache(maxsize=1)
def model_health() -> dict:
    """Model-health panel data (read-only; one contract for the panel).

    Surfaces what the serving models are claiming vs what the held-out
    evaluation showed:
      - degradation : per dim x horizon delta MAE / R2 / Spearman, the
                      split-conformal band (nominal 80% coverage + achieved)
                      and the measurement noise floor (central sigma).
      - pturn       : per horizon C1 XGB ROC-AUC / PR-AUC / Brier / ECE plus
                      train vs test realized turn rates (the reliability band).
      - defect      : per dim x horizon operational capture@1/5/10%.
      - provenance  : artifact contract versions (honesty: which report).
    Every number maps 1:1 to a committed benchmark artifact - nothing is
    recomputed here and nothing is invented. `predicted` flag notes that the
    degradation panel uses the delta model's own evaluation, not a live probe.
    """
    artefact = trajectory_artefact()
    degradation = {}
    for dim, hs in artefact.get("1_delta_metrics", {}).items():
        degradation[dim] = {}
        for h, m in sorted(hs.items()):
            noise = _noise_floor_mm(dim)
            conf = artefact.get("3_conformal_80pct", {}).get(dim, {}).get(h, {})
            op = artefact.get("4_operational_capture", {}).get(dim, {}).get(h, {})
            degradation[dim][h] = {
                "mae_mm": m.get("mae_mm") or m.get("delta_mae_mm"),
                "r2": m.get("delta_r2") if "delta_r2" in m else m.get("r2"),
                "spearman": m.get("delta_spearman") if "delta_spearman" in m else m.get("spearman"),
                "noise_floor_mm": noise,
                "conformal": {
                    "level": 0.8,
                    "width_mm": conf.get("conformal_width_mm"),
                    "coverage": conf.get("coverage"),
                    "n_fit": conf.get("n_fit"), "n_cal": conf.get("n_cal"), "n_test": conf.get("n_test"),
                },
                "capture_at_1_pct": op.get("capture_1%"),
                "capture_at_5_pct": op.get("capture_5%"),
                "capture_at_10_pct": op.get("capture_10%"),
            }

    pturn = {}
    bench = json.loads(PTURN_BENCH.read_text()) if PTURN_BENCH.exists() else {}
    for h, hb in bench.get("horizons", {}).items():
        m = hb.get("models", {}).get("C1_xgb")
        if not m:
            continue
        pturn[h] = {
            "roc_auc": m.get("roc_auc"), "pr_auc": m.get("pr_auc"),
            "brier": m.get("brier"), "ece": m.get("ece"),
            "n_test": m.get("n_test"),
            "turn_rate_train": m.get("turn_rate_train"), "turn_rate_test": m.get("turn_rate_test"),
        }

    return {
        "degradation": degradation,
        "pturn": pturn,
        "provenance": {
            "trajectory_artefact_contract": artefact.get("contract"),
            "trajectory_artefact_task": artefact.get("task"),
            "turn_probability_contract": bench.get("contract"),
            "artefact_generated": artefact.get("generated_at"),
            "predicted": True,
            "note": ("Every number maps 1:1 to the committed benchmark artifacts "
                     "(trajectory_product_analysis.json + turn_probability_benchmark.json). "
                     "This is the model's self-assessment on held-out splits, not a live probe."),
        },
    }


def fleet_locos() -> dict:
    """Ordered loco list for the switcher, from the P1.1 fleet snapshot.

    Returns a stable ordering (by loco number) of every distinct locomotive in
    the snapshot with its wheelset count and latest-measurement recency, so
    the UI can offer prev/next + dropdown navigation between locos.
    """
    df = _snapshot_df()
    if df is None or df.empty or "loco_number" not in df:
        return {"error": "fleet snapshot not built or has no loco identity",
                "locos": [], "total": 0}
    grp = (df.dropna(subset=["loco_number"])[["loco_number", "wheelset_equipment_id", "staleness_days"]]
             .groupby("loco_number"))
    locos = []
    for loco_number, g in grp:
        locos.append({
            "loco_number": str(loco_number),
            "n_wheelsets": int(len(g)),
            "n_recent": int((g["staleness_days"] <= 90).sum()),
            "locos_note": "staleness_days recency is a measurement signal, not a proven fit",
        })
    locos.sort(key=lambda r: r["loco_number"])
    return {"locos": locos, "total": len(locos),
            "error": None, "note": "ordered by loco number; recency is measurement-based"}


def _turn_calibration() -> dict:
    """Phase 4 empirical reliability band per P(turn) horizon.

    Map: horizon -> {bin_edges, bin_rates, train_prevalence}. Computed in
    run_turn_probability_benchmark.py on the C1 training split (the serving C1
    uses the same config + train split, so the band carries over). `calibrated`
    = the realized train event rate of the score decile a raw score falls into.
    """
    if not PTURN_BENCH.exists():
        return {}
    try:
        data = json.loads(PTURN_BENCH.read_text())
        out = {}
        for h, block in data.get("horizons", {}).items():
            cal = block.get("models", {}).get("C1_xgb", {}).get("calibration")
            if cal and cal.get("bin_edges") and cal.get("bin_rates"):
                out[int(h)] = cal
        return out
    except (KeyError, TypeError, ValueError):
        return {}


def calibrate_turn(h: int, p: float) -> tuple[int, float | None]:
    """Map a raw P(turn) score to (decile, realized event rate) via the Phase 4 band."""
    cal = _turn_calibration().get(int(h))
    if not cal or p is None or not np.isfinite(p):
        return 0, None
    edges = cal["bin_edges"]; rates = cal["bin_rates"]
    if not edges or not rates:
        return 0, None
    dec = int(np.clip(np.digitize(p, edges[1:-1]), 0, len(rates) - 1))
    return dec, rates[dec]


def turn_attribution(wheelset_id: int, target: str = "turn") -> dict | None:
    """Phase 4 per-wheel SHAP attribution for the latest scored measurement.

    target: "turn" (shipping) or "root" (exploratory - sparse, see report).
    Returns None when the wheelset is not in the Phase 4 scored batch.
    """
    path = V4_TURN_ATTRIB if target == "turn" else V4_ROOT_ATTRIB
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=[
        "wheelset_equipment_id", "measurement_record_id", "locomotive_id",
        "measurement_timestamp", "prob", "risk", "conf_decile",
        "conf_empirical_rate", "train_prevalence", "realized_event",
        "contributors"])
    rows = df[df["wheelset_equipment_id"] == wheelset_id]
    if rows.empty:
        return None
    r = rows.sort_values("measurement_timestamp").iloc[-1]
    return {
        "target": target,
        "wheelset_equipment_id": wheelset_id,
        "measurement_record_id": int(r["measurement_record_id"]),
        "locomotive_id": int(r["locomotive_id"]) if pd.notna(r["locomotive_id"]) else None,
        "anchor": pd.Timestamp(r["measurement_timestamp"]).isoformat(),
        "probability": round(float(r["prob"]), 4),
        "risk": str(r["risk"]),
        "conf_decile": int(r["conf_decile"]),
        "conf_empirical_rate": (round(float(r["conf_empirical_rate"]), 4)
                                if r["conf_empirical_rate"] is not None else None),
        "train_prevalence": round(float(r["train_prevalence"]), 6),
        "realized_event": (None if pd.isna(r["realized_event"])
                           else bool(float(r["realized_event"]))),
        "contributors": list(r["contributors"]),
    }


def _artifact_version() -> str:
    """Deterministic serving-model version from the on-disk artifacts.

    A content hash of the feature schema + manifest (+ model file sizes so a
    retrained model bumps the version). Includes the wear-rate head + champion
    when present so a retrained/changed Option-3 model also bumps the version.
    Short enough for a footnote, stable across restarts, and changes whenever
    the artifacts change.
    """
    parts = []
    for f in ("features.json", "manifest.json"):
        p = DEG_DIR / f
        parts.append(p.read_bytes() if p.exists() else b"")
    for dim in DIMM:
        for h in HORIZONS:
            p = DEG_DIR / f"model_{dim}_{h}d.joblib"
            parts.append(str(p.stat().st_size).encode() if p.exists() else b"")
    for f in ("features.json", "manifest.json", "champion.json"):
        p = RATE_DIR / f
        parts.append(p.read_bytes() if p.exists() else b"")
    for dim in DIMM:
        p = RATE_DIR / f"model_{dim}.joblib"
        parts.append(str(p.stat().st_size).encode() if p.exists() else b"")
    return hashlib.sha256(b"|".join(parts)).hexdigest()[:10]


def degradation_meta() -> dict:
    """Model version, train cutoff and target mode for the degradation service."""
    feats = json.loads((DEG_DIR / "features.json").read_text())
    mf = json.loads((DEG_DIR / "manifest.json").read_text())
    targets = {m["target"] for m in mf.get("models", [])}
    mor = model_of_record()
    champ = rate_champion()
    return {
        "model_version": _artifact_version(),
        "train_cutoff": feats.get("train_cutoff"),
        "n_train": feats.get("n_train_rows"),
        "target_mode": "delta" if targets == {"delta"} else "level",
        "task": mf.get("task"),
        "model_of_record": mor,
        "model_of_record_agg": champ.get("aggregate_model_of_record",
                                         "per_horizon_xgb"),
        "wear_rate": {
            "present": bool(RATE_DIR.exists()),
            "basis": champ.get("basis"),
            "decay_k": champ.get("decay_k"),
            "agg_served_mae_current_mm": champ.get("agg_served_mae_current_mm"),
            "agg_served_mae_rate_calibrated_mm": champ.get("agg_served_mae_rate_calibrated_mm"),
        },
    }


def feature_coverage(feat: dict, num_feats: list[str]) -> float | None:
    """Share of numeric serving inputs that are present and finite (0..1)."""
    if not num_feats:
        return None
    present = 0
    for c in num_feats:
        v = feat.get(c)
        if v is not None and not pd.isna(v) and np.isfinite(float(v)):
            present += 1
    return round(present / len(num_feats), 4)


def validate_serving() -> list[str]:
    """Fail-fast check of the serving artifacts at load (not request time).

    Raises RuntimeError on a missing file / malformed schema so a broken
    deployment surfaces at startup, not as a KeyError on the first request.
    Returns a list of warnings (non-fatal, e.g. unknown dims in manifest).
    """
    warnings: list[str] = []
    for name, d, feats_key, dims, horizons in (
        ("degradation", DEG_DIR, "num_feats", DIMM, HORIZONS),
        ("turn_probability", PTURN_DIR, "num_feats", None, None),
    ):
        feats_p = d / "features.json"
        man_p = d / "manifest.json"
        if not feats_p.exists():
            raise RuntimeError(f"[{name}] missing features.json: {feats_p.relative_to(ROOT)}")
        if not man_p.exists():
            raise RuntimeError(f"[{name}] missing manifest.json: {man_p.relative_to(ROOT)}")
        feats = json.loads(feats_p.read_text())
        for key in ("num_feats", "cat_feats"):
            if key not in feats or not feats[key]:
                raise RuntimeError(f"[{name}] features.json missing/empty {key}")
        if "train_cutoff" not in feats:
            warnings.append(f"[{name}] features.json has no train_cutoff")
        if not (d / "encoder.joblib").exists():
            raise RuntimeError(f"[{name}] missing encoder.joblib")
        manifest = json.loads(man_p.read_text())
        models = manifest.get("models", [])
        if not models:
            raise RuntimeError(f"[{name}] manifest has no models")
        for m in models:
            if not (d / m["path"]).exists():
                raise RuntimeError(f"[{name}] manifest model missing: {m['path']}")
        if name == "degradation":
            have = {(m["dim"], int(m["horizon"])) for m in models}
            want = {(dim, h) for dim in DIMM for h in HORIZONS}
            missing = want - have
            if missing:
                raise RuntimeError(f"[degradation] manifest missing models: {sorted(missing)}")
    # wear-rate head: required for every dim the champion routes to it
    for dim in model_of_record():
        if model_of_record()[dim] == "wear_rate":
            for f in ("features.json", "encoder.joblib", "manifest.json",
                      "champion.json", f"model_{dim}.joblib"):
                p = RATE_DIR / f
                if not p.exists():
                    raise RuntimeError(
                        f"[degradation_rate] champion routes {dim} to wear_rate "
                        f"but {p.relative_to(ROOT)} is missing")
    return warnings


def capabilities() -> dict:
    """Feature flags for the UI. `p0_2_dia_fix` gates forecast rendering."""
    try:
        meta = degradation_meta()
    except Exception:
        meta = {}
    return {
        "p0_2_dia_fix": meta.get("target_mode") == "delta",
        "degradation_serving": {
            "model_version": meta.get("model_version"),
            "train_cutoff": meta.get("train_cutoff"),
            "n_train": meta.get("n_train"),
            "target_mode": meta.get("target_mode"),
            "model_of_record": meta.get("model_of_record"),
        },
        "limits": limits_register(),
    }


def _feature_vector(feat_row: dict, num_feats, cat_feats, enc) -> np.ndarray:
    Xn = np.array([[feat_row.get(c, np.nan) for c in num_feats]], dtype=float)
    cat = np.array([[str(feat_row.get(c, "NA")) if feat_row.get(c) is not None
                     and not pd.isna(feat_row.get(c)) else "NA"
                     for c in cat_feats]])
    Xc = enc.transform(cat)
    return np.hstack([Xn, Xc])


def predict_degradation(wheelset_id: int, anchor=None) -> dict:
    if anchor is None:
        anchor = latest_anchor(wheelset_id)
    if anchor is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "forecasts": []}
    fr = extract_features(wheelset_id, anchor)
    if fr is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": anchor, "forecasts": []}
    svc = degradation_models()
    meta = degradation_meta()
    cov = feature_coverage(fr, svc["num_feats"])
    X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
    fc = []
    for dim in DIMM:
        current = fr.get(f"mean_{dim}")
        dcur = current if current is not None and np.isfinite(current) else None
        raw = _horizon_deltas(dim, fr)
        mono = _no_turn_monotone(dim, raw) if dcur is not None else raw
        for h in HORIZONS:
            delta = mono.get(h)
            value = round(float(dcur + delta), 4) if dcur is not None and delta is not None else None
            width = _conformal_width_mm(dim, h)
            flags = _physics_flags(dim, current, value)
            fc.append({"horizon": h, "dim": dim, "value": value,
                       "delta": round(delta, 4) if delta is not None else None,
                       "current": round(float(current), 4)
                       if current is not None and np.isfinite(current) else None,
                       "low": round(value - width, 4) if value is not None and width is not None else None,
                       "high": round(value + width, 4) if value is not None and width is not None else None,
                       "implausibility_flag": flags[0] if flags else None,
                       "model_version": meta.get("model_version"),
                       "train_cutoff": meta.get("train_cutoff"),
                       "model_of_record": meta.get("model_of_record", {}).get(dim),
                       "feature_coverage": cov,
                       "subgroup_flags": subgroup_flags(fr, dim, h)})
    return {"wheelset_equipment_id": wheelset_id, "anchor": anchor,
            "model": meta, "feature_coverage": cov, "forecasts": fc}


def predict_pturn(wheelset_id: int, anchor=None) -> dict:
    if anchor is None:
        anchor = latest_anchor(wheelset_id)
    if anchor is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "probabilities": []}
    fr = extract_features(wheelset_id, anchor)
    if fr is None:
        return {"wheelset_equipment_id": wheelset_id, "anchor": anchor, "probabilities": []}
    svc = pturn_models()
    rel = pturn_reliability()
    X = _feature_vector(fr, svc["num_feats"], svc["cat_feats"], svc["enc"])
    out = []
    for h in svc["models"]:
        m = svc["models"][h]
        p = float(m.predict_proba(X)[0, 1])
        r = rel.get(int(h), {})
        dec, cal_rate = calibrate_turn(h, p)
        out.append({"horizon": h, "probability": round(p, 4),
                    "calibrated_probability": round(cal_rate, 4) if cal_rate is not None else None,
                    "conf_decile": dec if cal_rate is not None else None,
                    "calibration_source": "phase4_empirical_deciles",
                    "turn_rate_train": svc["turn_rate_train"].get(h),
                    "roc_auc": r.get("roc_auc"),
                    "turn_rate_test": r.get("turn_rate_test")})
    return {"wheelset_equipment_id": wheelset_id, "anchor": anchor,
            "probabilities": out}


@lru_cache(maxsize=1)
def trajectory_artefact() -> dict:
    if not TRAJ_ARTEFACT.exists():
        return {}
    return json.loads(TRAJ_ARTEFACT.read_text())


def _conformal_width_mm(dim: str, h: int) -> float | None:
    a = trajectory_artefact()
    try:
        return float(a["3_conformal_80pct"][dim][f"{h}d"]["conformal_width_mm"])
    except (KeyError, TypeError):
        return None


def _noise_floor_mm(dim: str) -> float | None:
    a = trajectory_artefact()
    try:
        return float(a["2_noise_floor"][dim]["central_sigma_mm"])
    except (KeyError, TypeError):
        return None


def _no_turn_monotone(dim: str, deltas: dict[int, float | None]) -> dict[int, float | None]:
    """Physics-valid, monotone serving path: value at H 'if no turn happens'.

    The horizon models (30/90/180 d) are trained independently, so together
    they can produce an impossible path inside one segment — root/flange/thread
    decreasing or diameter increasing. Within a segment wear only grows and
    diameter only shrinks, so each delta is signed-clamped (>=0 for wear,
    <=0 for dia) and the cumulative path is made monotone across horizons.
    This constrains only the SERVING output (the no-turn claim), never the
    training targets.
    """
    down = dim == "wsmDia"
    out: dict[int, float | None] = {}
    prev = 0.0
    for h in sorted(deltas):
        d = deltas.get(h)
        if d is None or not np.isfinite(d):
            out[h] = None
            continue
        if down:
            prev = min(prev, min(d, 0.0))
        else:
            prev = max(prev, max(d, 0.0))
        out[h] = prev
    return out


def _conformal_table() -> dict:
    """Split-conformal band metadata per (dim, horizon) for the text readout.

    `level` = nominal coverage of the band (0.80); `width_mm` = calibrated
    half-width; `coverage` = empirical test-set coverage actually achieved, so
    the UI can say e.g. "± 0.37 mm (80% band, empirical 83%)".
    """
    a = trajectory_artefact().get("3_conformal_80pct", {})
    out = {}
    for dim, hs in a.items():
        out[dim] = {}
        for h, m in hs.items():
            out[dim][h] = {
                "level": 0.8,
                "width_mm": m.get("conformal_width_mm"),
                "coverage": m.get("coverage"),
            }
    return out


def _crossing_days(times: list[int], values: list[float | None],
                   limit: float, direction: str) -> float | None:
    """First day a piecewise-linear (t, value) path crosses `limit`.

    direction "down": value falls to the limit (dia shrinks to 1016).
    direction "up":   value rises to the limit (flange/root/tread wear grow to
                      their approved Wrpld limits: 3.0 / 6.0 / 6.5 mm).
    Returns None if the limit is not crossed within the provided times.
    """
    first = True
    prev_t = prev_v = None
    for t, v in zip(times, values):
        if v is None or not np.isfinite(v):
            first = True
            prev_t = prev_v = None
            continue
        if not first and prev_v is not None and prev_t is not None:
            lo_v, hi_v = sorted((prev_v, v))
            if direction == "down" and lo_v <= limit <= hi_v:
                # interpolate when the falling edge crosses
                if v != prev_v:
                    frac = (prev_v - limit) / (prev_v - v)
                    return float(prev_t + frac * (t - prev_t))
            elif direction == "up" and lo_v <= limit <= hi_v:
                if v != prev_v:
                    frac = (limit - prev_v) / (v - prev_v)
                    return float(prev_t + frac * (t - prev_t))
        first = False
        prev_t, prev_v = t, v
    return None


def _time_to_limit(dim: str, cur: float | None,
                   pred: dict, low: dict, high: dict) -> dict | None:
    """Time-to-limit for one dim from anchor + 30/90/180 forecasts.

    Builds three piecewise-linear paths (point, interval-lo, interval-hi) over
    the horizon grid and finds the first crossing of the approved limit. Only
    dims with `status != pending` and a numeric limit participate; wear dims
    return None until engineering signs off numeric thresholds.
    """
    reg = LIMIT_REGISTER.get(dim)
    if reg is None or reg.get("limit_mm") is None or cur is None or not np.isfinite(cur):
        return None
    band_ok = any(low.get(h) is not None and high.get(h) is not None for h in TTL_HORIZONS)
    ttl: dict = {
        "dim": dim,
        "limit_mm": reg["limit_mm"],
        "direction": reg["direction"],
        "label": reg["label"],
        "limit_status": reg["status"],
        "current_mm": round(float(cur), 4),
        "predicted_at": {}, "interval_lo": {}, "interval_hi": {},
        "days_to_limit_point": None,
        "days_to_limit_lo": None,
        "days_to_limit_hi": None,
        "status": "beyond_horizon",
        "note": (f"days-to-limit from serving delta forecasts at 30/90/180; "
                 f"piecewise-linear; limit {reg['limit_mm']} mm ({reg['label']}, "
                 f"status={reg['status']}). "
                 + ("Conformal interval edges are calibrated, so the band "
                    "reports a conservative earliest crossing."
                    if band_ok else
                    "No calibrated conformal band for this dim, so only the "
                    "point path is reported.")),
    }
    times = list(TTL_HORIZONS)
    for h in TTL_HORIZONS:
        p = pred.get(h)
        ttl["predicted_at"][h] = round(float(p), 4) if p is not None and np.isfinite(p) else None
        ttl["interval_lo"][h] = round(float(low[h]), 4) if low.get(h) is not None and np.isfinite(low[h]) else None
        ttl["interval_hi"][h] = round(float(high[h]), 4) if high.get(h) is not None and np.isfinite(high[h]) else None

    limit = reg["limit_mm"]
    direction = reg["direction"]

    # Already at/beyond the limit now
    if (direction == "down" and cur <= limit) or (direction == "up" and cur >= limit):
        ttl["days_to_limit_point"] = 0.0
        ttl["days_to_limit_lo"] = 0.0
        ttl["days_to_limit_hi"] = 0.0
        ttl["status"] = "at_limit"
        return ttl

    point = _crossing_days([0] + times, [cur] + [pred.get(h) for h in times], limit, direction)
    lo = _crossing_days([0] + times, [cur] + [low.get(h) for h in times], limit, direction)
    hi = _crossing_days([0] + times, [cur] + [high.get(h) for h in times], limit, direction)

    ttl["days_to_limit_point"] = round(point, 1) if point is not None else None
    # conservative edge = whichever band edge reaches the limit sooner
    edges = [d for d in (lo, hi) if d is not None]
    if edges:
        ttl["days_to_limit_lo"] = round(min(edges), 1)
        ttl["days_to_limit_hi"] = round(max(edges), 1) if len(edges) > 1 else None
    if point is not None:
        ttl["status"] = "within_horizon"
    return ttl


def _limit_summary_note() -> str:
    """Honest summary of which limits are registered, approved or pending."""
    approved = [f"{d} {r['limit_mm']:g} mm ({r['label']})"
                for d, r in LIMIT_REGISTER.items()
                if r.get("limit_mm") is not None and r.get("status") != "pending"]
    pending = [d for d, r in LIMIT_REGISTER.items() if r.get("limit_mm") is None]
    base = ("Time-to-limit is only defined for approved limits. "
            + (f"Approved: {', '.join(approved)}. " if approved else "")
            + (f"Pending C&W/standards sign-off (not reported): {', '.join(pending)}."
               if pending else "All registered limits approved."))
    return base


def operational_capture() -> dict:
    """Read operational capture@k from the trajectory artefact (turn-within-H proxy).

    Success = wheelset turned within H days (confirmed lifecycle post_ts in
    (t, t+H]); ranked by predicted delta for the dim at horizon H. Censored
    anchors (no turn AND no later measurement) are dropped. capture@1/5/10% =
    share of turned wheelsets found in the top k% by predicted delta.
    """
    a = trajectory_artefact().get("4_operational_capture", {})
    by_dim = {}
    for dim, horizons in a.items():
        by_dim[dim] = {}
        for h, cell in horizons.items():
            if cell is None:
                continue
            by_dim[dim][h] = {
                "n_label": int(cell.get("n_label", 0)),
                "turn_rate": cell.get("turn_rate"),
                "capture": {k: v for k, v in cell.items()
                            if k.startswith("capture_")},
            }
    return {
        "task": "operational capture@k (flange/root/tread)",
        "source": "trajectory_product_analysis.json $4",
        "label": ("share of wheelsets turned within H days captured in the top k% "
                  "ranking by predicted delta"),
        "by_dim": by_dim,
        "note": ("Proxy from the trajectory artefact: label = confirmed lifecycle "
                 "turn completes within (t, t+H]; censored anchors dropped. "
                 "Turn-within-H is shed-maintenance behaviour, NOT an engineering "
                 "failure threshold — it never ranks wheelsets on its own."),
    }


def _delta_metrics_slim() -> dict:
    a = trajectory_artefact().get("1_delta_metrics", {})
    out = {}
    for dim, hs in a.items():
        out[dim] = {f"{h}d": {
            "mae_mm": m.get("mae_mm"),
            "delta_r2": m.get("delta_r2"),
            "delta_spearman": m.get("delta_spearman"),
        } for h, m in hs.items()}
    return out


def _physics_flags(dim: str, current: float | None, predicted: float | None) -> list[str]:
    if predicted is None or current is None or not np.isfinite(current) or not np.isfinite(predicted):
        return []
    if dim == "wsmDia" and predicted > current + DIA_INC_TOL:
        return ["increasing_diameter"]
    if dim in WEAR_DIMS and predicted < current - WEAR_BETTER_TOL:
        return ["wear_better_than_current"]
    return []
    if dim == "wsmDia" and predicted > current + DIA_INC_TOL:
        return ["increasing_diameter"]
    if dim in WEAR_DIMS and predicted < current - WEAR_BETTER_TOL:
        return ["wear_better_than_current"]
    return []


def turn_reset_policy(w: pd.DataFrame, p: int,
                      turns: pd.DataFrame | None = None,
                      t_arr: np.ndarray | None = None) -> dict:
    """Deterministic TURN/RESET operator (Lever 1) at one anchor row.

    Rule-based restored-state detection (maintenance policy, NOT ML). A wheelset
    is in a RESTORED state when its own measurement row is a lifecycle boundary:

      - turn:        turning_record AND dia cut in [TURN_CUT_MIN, 25] mm AND
                     flange-or-root restored >= WEAR_RESTORE_MM (the same event
                     rule build_lifecycle_segments uses); the row is the
                     POST-TURN (fresh) measurement.
      - replacement: wsmProvDate change / wheel-age reset / confirmed dia
                     up-jump (the segment reconstructor's replacement rule).

    In a restored state the wear path must CONTINUE FROM the restored level, not
    extrapolate the reset as continuous wear. This policy never invents facts:
    `restored_state` is true only when the anchor's own row is a boundary.

    Returns a dict with:
      condition       = "restored" | "no_reset"
      boundary_kind   = "turn" | "replacement" | None
      cut_dia_mm      = pre - post mean diameter (only meaningful for a turn)
      restore         = {dim: post-turn level} per WEAR dim + wsmDia
      restore_claimed = true iff the anchor row is a boundary
    """
    r = w.iloc[p]
    seg_id_col = w["seg_id"].to_numpy(dtype="int64")
    is_turn = bool(r.get("turn_event", False))
    is_repl = bool(r.get("replacement", False))
    boundary_kind = "turn" if is_turn else ("replacement" if is_repl else None)

    cut = None
    restore = {}
    if boundary_kind == "turn":
        prev_dia = r.get("prev_wsmDia")
        cur_dia = r.get("mean_wsmDia")
        if np.isfinite(prev_dia) and np.isfinite(cur_dia):
            cut = round(float(prev_dia - cur_dia), 3)
    for dim in ("wsmDia", "wsmFlange", "wsmRoot", "wsmThread"):
        v = r.get(f"mean_{dim}")
        restore[dim] = round(float(v), 4) if v is not None and np.isfinite(v) else None

    return {
        "condition": "restored" if boundary_kind else "no_reset",
        "boundary_kind": boundary_kind,
        "cut_dia_mm": cut,
        "restore": restore,
        "restore_claimed": boundary_kind is not None,
    }


def _turn_markers(wheelset_id: int, asof: pd.Timestamp) -> list[dict]:
    """Turn/replacement markers from the confirmed lifecycle turns table.

    Each marker carries the pre/post profile state per dim plus the diameter
    cut, so a renderer (ECharts or Matplotlib) never needs the raw tables.
    Only turns whose post_ts is <= asof are included (the chart is anchored).
    """
    try:
        turns = pd.read_parquet(TURNS)
    except Exception:
        return []
    t = turns[turns["wheelset_equipment_id"] == wheelset_id].sort_values("post_ts")
    if t.empty:
        return []
    out = []
    for no, (_, r) in enumerate(t.iterrows(), start=1):
        post = pd.Timestamp(r["post_ts"])
        if post > asof:
            continue
        pre = pd.Timestamp(r["pre_ts"]) if pd.notna(r.get("pre_ts")) else post
        out.append({
            "turn_no": no,
            "pre_ts": pre,
            "post_ts": post,
            "segment_index": _f(r.get("segment_index")),
            "days_between": _f(r.get("days_between")),
            "pre_wsmDia": _f(r.get("pre_wsmDia")),
            "post_wsmDia": _f(r.get("post_wsmDia")),
            "dia_cut": _f(r.get("cut_dia")),
            "pre_wsmFlange": _f(r.get("pre_wsmFlange")),
            "post_wsmFlange": _f(r.get("post_wsmFlange")),
            "pre_wsmRoot": _f(r.get("pre_wsmRoot")),
            "post_wsmRoot": _f(r.get("post_wsmRoot")),
            "pre_wsmThread": _f(r.get("pre_wsmThread")),
            "post_wsmThread": _f(r.get("post_wsmThread")),
        })
    return out


def _limiting_dim_provenance(wheelset_id: int) -> dict | None:
    """Gold-contract limiting-dim attribution for one wheelset.

    Joins the current fleet snapshot's `limiting_dim_verified` /
    `limiting_dim_source` columns (emitted from the interval-context contract).
    Returns None when the wheelset is not in the snapshot. Never re-derives the
    argmax or fleet priors here - the contract is the single source of truth.
    """
    try:
        df = _snapshot_df()
    except Exception:
        return None
    if df is None or df.empty:
        return None
    row = df[df["wheelset_equipment_id"] == int(wheelset_id)]
    if row.empty:
        return None
    r = row.iloc[0]
    dim = r.get("limiting_dim_verified")
    heur = r.get("limiting_dim")
    return {
        "limiting_dim_verified": str(dim) if pd.notna(dim) else None,
        "limiting_dim_source": r.get("limiting_dim_source") if pd.notna(r.get("limiting_dim_source")) else None,
        "limiting_dim_heuristic": str(heur) if pd.notna(heur) else None,
        "limiting_reason": r.get("limiting_reason") if pd.notna(r.get("limiting_reason")) else None,
        "prior": _f(r.get("limiting_dim_prior")),
        "contract": "fleet_snapshot_v1",
    }


def _segment_bands(w: pd.DataFrame) -> list[dict]:
    """Lifecycle segment bands for one wheelset's full history.

    Contiguous runs of the same `seg_id` become one band with start/end ts,
    boundary kind at its end (turn / replacement / None), and the number of
    measurements inside. Used by the continuous-lifecycle chart to shade each
    segment and put a marker where the current forecast anchor sits.
    """
    if w.empty or "seg_id" not in w:
        return []
    bands = []
    for seg_id, g in w.groupby("seg_id", sort=False):
        g = g.sort_values("measurement_timestamp")
        band = {
            "segment_index": int(seg_id) if pd.notna(seg_id) else None,
            "start_ts": pd.Timestamp(g.iloc[0]["measurement_timestamp"]),
            "end_ts": pd.Timestamp(g.iloc[-1]["measurement_timestamp"]),
            "n_measurements": int(len(g)),
            "boundary_kind": None,
        }
        last = g.iloc[-1]
        band["boundary_kind"] = (
            "turn" if bool(last.get("turn_event", False))
            else "replacement" if bool(last.get("replacement", False)) else None)
        bands.append(band)
    return bands


def trajectory(wheelset_id: int, asof: pd.Timestamp | None = None) -> dict:
    """Chart-data contract for the trajectory panel (trajectory_chart_v1).

    Built for a single anchor (default = latest measurement; `asof` re-anchors
    at a historical measurement). Wear dims are primary; wsmDia is derived and
    flagged when the forecast would increase it. All values are levels
    (predicted = current + delta); physics flags are reported, never clipped.
    """
    wes_all = load_wes()
    w = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id].sort_values(
        "measurement_timestamp").reset_index(drop=True)
    if w.empty:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None, "asof": None,
                "contract": "trajectory_chart_v1", "model": None, "dims": [],
                "feature_coverage": None,
                "delta_metrics": {}, "conformal": {}, "time_to_limit_summary": None, "note": None}

    anchor = asof if asof is not None else pd.Timestamp(w.iloc[-1]["measurement_timestamp"])
    t = pd.to_datetime(w["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    anchor_ns = np.datetime64(pd.Timestamp(anchor), "us")
    pos = np.where(t_arr == anchor_ns)[0]
    if len(pos) == 0:
        return {"wheelset_equipment_id": wheelset_id, "anchor": None,
                "asof": pd.Timestamp(anchor),
                "contract": "trajectory_chart_v1", "model": None, "dims": [],
                "feature_coverage": None,
                "delta_metrics": {}, "conformal": {}, "time_to_limit_summary": None,
                "note": "as-of is not a measurement timestamp"}
    p = int(pos[0])

    fr = extract_features(wheelset_id, pd.Timestamp(anchor), w=w)
    svc = degradation_models()
    meta = degradation_meta()
    cov = feature_coverage(fr, svc["num_feats"]) if fr is not None else None
    adapt = wheel_adaptation_at(wheelset_id, pd.Timestamp(anchor))
    deg = {}
    if fr is not None:
        for dim in DIMM:
            cur = fr.get(f"mean_{dim}")
            deg[dim] = {"current": cur, "delta": {}, "predicted": {}, "adaptation": {}}
            raw = _horizon_deltas(dim, fr)
            for h in HORIZONS:
                delta = raw.get(h)
                predicted = cur + delta if delta is not None and cur is not None and np.isfinite(cur) else None
                adj = adapt.get((dim, h)) if adapt else None
                if adj and adj["prior_n"] >= ADAPT_MIN_N and adj["bias"] is not None \
                        and not adj["boundary"] and adapt_applies(dim):
                    predicted = predicted + adj["bias"] if predicted is not None else predicted
                    deg[dim]["adaptation"][h] = {
                        "prior_n": adj["prior_n"], "bias_mm": adj["bias"], "applied": True}
                else:
                    deg[dim]["adaptation"][h] = {
                        "prior_n": adj["prior_n"] if adj else 0,
                        "bias_mm": adj["bias"] if adj else None, "applied": False}
                deg[dim]["delta"][h] = delta
                deg[dim]["predicted"][h] = predicted
            # Monotone no-turn path: reconcile the three independent horizon
            # models so the trajectory can never show wear decreasing / dia
            # increasing inside a segment. Applied AFTER adaptation so it is
            # the final serving path that is constrained, not the raw deltas.
            if cur is not None and np.isfinite(cur):
                rawd = {h: (deg[dim]["predicted"][h] - cur)
                        if deg[dim]["predicted"][h] is not None else None
                        for h in HORIZONS}
                clamped = _no_turn_monotone(dim, rawd)
                for h in HORIZONS:
                    dd = clamped.get(h)
                    if dd is not None:
                        deg[dim]["predicted"][h] = round(float(cur + dd), 6)
                        deg[dim]["delta"][h] = round(float(dd), 6)

    # observed history up to (and including) the anchor
    seg_id = w["seg_id"].to_numpy(dtype="int64") if "seg_id" in w else w.get("seg_id")
    dims = []
    for dim in DIMM:
        vals = w[f"mean_{dim}"].to_numpy(dtype=float)
        cur = deg[dim]["current"] if dim in deg else None
        obs = []
        for i in range(p + 1):
            v = vals[i]
            if np.isfinite(v):
                obs.append({
                    "ts": pd.Timestamp(t.iloc[i]),
                    "value": round(float(v), 4),
                    "segment_index": int(seg_id[i]) if seg_id is not None else None,
                    "turn_event": bool(w.iloc[i].get("turn_event", False)),
                    "replacement": bool(w.iloc[i].get("replacement", False)),
                })
        forecasts = []
        flags = set()
        pred_map, low_map, high_map = {}, {}, {}
        for h in HORIZONS:
            pred = deg[dim]["predicted"].get(h) if dim in deg else None
            width = _conformal_width_mm(dim, h)
            pred_map[h], low_map[h], high_map[h] = pred, (pred - width) if (pred is not None and width is not None) else None, (pred + width) if (pred is not None and width is not None) else None
            forecasts.append({
                "dim": dim, "horizon": h,
                "asof_ts": pd.Timestamp(anchor) + pd.Timedelta(days=h),
                "current": round(float(cur), 4) if cur is not None and np.isfinite(cur) else None,
                "delta": round(float(deg[dim]["delta"][h]), 4)
                if dim in deg and deg[dim]["delta"].get(h) is not None else None,
                "predicted": round(float(pred), 4) if pred is not None else None,
                "low": round(float(low_map[h]), 4) if low_map[h] is not None else None,
                "high": round(float(high_map[h]), 4) if high_map[h] is not None else None,
                "model_version": meta.get("model_version"),
                "train_cutoff": meta.get("train_cutoff"),
                "model_of_record": meta.get("model_of_record", {}).get(dim),
                "feature_coverage": cov,
                "wheel_adaptation": deg[dim]["adaptation"].get(h, {
                    "prior_n": 0, "bias_mm": None, "applied": False}),
                "subgroup_flags": subgroup_flags(fr, dim, h) if fr is not None else [],
            })
            flags.update(_physics_flags(dim, cur, pred))
        time_to_limit = _time_to_limit(dim, cur, pred_map, low_map, high_map)

        # realised: future within-segment measurements inside each horizon
        realised = []
        for h in HORIZONS:
            hi = int(np.searchsorted(t_arr, anchor_ns + h * DAY, side="right"))
            b = int(np.searchsorted(seg_id, seg_id[p], side="right")) if seg_id is not None else 0
            last_same = min(hi, b) - 1
            if last_same > p:
                actual = vals[last_same]
                pred = deg[dim]["predicted"].get(h) if dim in deg else None
                if np.isfinite(actual):
                    realised.append({
                        "dim": dim, "horizon": h,
                        "ts": pd.Timestamp(t.iloc[last_same]),
                        "actual": round(float(actual), 4),
                        "residual": round(float(actual - pred), 4) if pred is not None else None,
                        "observed_in_horizon": True,
                    })

        dims.append({
            "dim": dim,
            "observed": obs,
            "forecasts": forecasts,
            "realised": realised,
            "flags": sorted(flags),
            "noise_floor_mm": _noise_floor_mm(dim),
            "time_to_limit": time_to_limit,
        })

    # model metadata from the degradation serving manifest + features.json
    meta = None
    try:
        dm = degradation_meta()
        meta = {
            "task": dm.get("task"),
            "target_mode": "delta",
            "train_cutoff": dm.get("train_cutoff"),
            "n_train": dm.get("n_train"),
            "model_version": dm.get("model_version"),
            "model_of_record": dm.get("model_of_record"),
        }
    except Exception:
        pass

    # time-to-limit summary: only dims with an approved limit participate;
    # limiting dim = the one that reaches its limit soonest on the point path.
    ttl_rows = [d["time_to_limit"] for d in dims if d.get("time_to_limit")]
    limiting = None
    if ttl_rows:
        ranked = sorted(
            ttl_rows,
            key=lambda x: (x["days_to_limit_point"] is not None,
                           x["days_to_limit_point"] if x["days_to_limit_point"] is not None else 1e12))
        limiting = ranked[0]
    summary = {
        "status": limiting["status"] if limiting else "no_approved_limit",
        "limiting_dim": limiting["dim"] if limiting else None,
        "limit_mm": limiting["limit_mm"] if limiting else None,
        "limit_status": limiting["limit_status"] if limiting else None,
        "current_mm": limiting["current_mm"] if limiting else None,
        "days_to_limit_point": limiting["days_to_limit_point"] if limiting else None,
        "days_to_limit_lo": limiting["days_to_limit_lo"] if limiting else None,
        "days_to_limit_hi": limiting["days_to_limit_hi"] if limiting else None,
        "note": _limit_summary_note(),
    }

    # loco number + identity for full context in the contract
    loco_number = None
    try:
        wes_row = wes_all[wes_all["wheelset_equipment_id"] == wheelset_id]["LomNumber"].dropna()
        if len(wes_row):
            loco_number = str(wes_row.iloc[-1])
    except Exception:
        pass

    return {
        "wheelset_equipment_id": wheelset_id,
        "loco_number": loco_number,
        "anchor": pd.Timestamp(anchor),
        "asof": pd.Timestamp(anchor),
        "contract": "lifecycle_chart_v1",
        "units": {"length": "mm", "time": "days"},
        "model": meta,
        "feature_coverage": cov,
        "dims": dims,
        "turns": _turn_markers(wheelset_id, pd.Timestamp(anchor)),
        "turn_reset": turn_reset_policy(w, p),
        "segments": _segment_bands(w),
        "limiting_dim_provenance": _limiting_dim_provenance(wheelset_id),
        "delta_metrics": _delta_metrics_slim(),
        "conformal": _conformal_table(),
        "forecast_condition": "no_turn_within_horizon",
        "monotone_enforced": True,
        "time_to_limit_summary": summary,
        "note": ("Lifecycle chart contract (lifecycle_chart_v1): forecast = "
                 "anchor + delta, CONDITIONAL ON NO TURN within the horizon — a "
                 "physics-valid path constrained so wear never decreases (and "
                 "diameter never increases) across 30/90/180 d, applied after "
                 "wheelset adaptation. 80% split-conformal bands + noise floor "
                 "from the trajectory artefact; physics flags reported, never "
                 "clipped; turn markers carry pre/post profile state + dia "
                 "cut so renderers never read raw tables."),
    }


def loco_lookup(loco_number: str) -> pd.DataFrame:
    wes = load_wes()
    lom = str(loco_number).strip().lower()
    target = wes[wes["LomNumber"].astype(str).str.lower().eq(lom)]
    if target.empty:
        return pd.DataFrame()
    return target.drop_duplicates("wheelset_equipment_id")


def loco_summary(loco_number: str) -> dict:
    """Loco wheelset list with an honest measurement-recency split.

    There is NO equipment-assignment table in this dataset (only SQL
    extraction scripts under ml/sql); the only loco-stamp is the `LomNumber`
    on each WES measurement. Probe on 39186: A (ever on loco)=25,
    B (latest measurement still stamped this loco)=8 — including 638d/1098d
    stale rows — and C (latest + ≤90d)=6, which equals the physical Co-Co
    axle count. So "recently measured AND latest loco-stamp == this loco"
    is the defensible proxy; it is measurement recency, NOT a proven fit.

    Returns wheelsets grouped into:
    - wheelsets: recent (≤90d) wheelsets whose latest measurement still
      carries this loco  (is_recently_measured = True)
    - wheelsets_all: complete history (for the optional toggle later)
    """
    wes = load_wes()
    lom = str(loco_number).strip().lower()
    target = wes[wes["LomNumber"].astype(str).str.lower().eq(lom)]
    if target.empty:
        return {"loco_number": loco_number, "locomotive_id": None,
                "wheelsets": [], "n_wheelsets": 0, "n_wheelsets_current": 0,
                "n_wheelsets_historical": 0}
    
    rows = []
    rows_all = []
    seg = load_segments()
    turns = pd.read_parquet(TURNS)
    turns = turns[turns["wheelset_equipment_id"].isin(target["wheelset_equipment_id"])]
    
    reference_date = pd.Timestamp.now()
    RECENCY_THRESHOLD_DAYS = 90
    
    for (ws, grp) in target.sort_values("measurement_timestamp").groupby("wheelset_equipment_id"):
        last = grp.iloc[-1]
        meas_ts = pd.Timestamp(last["measurement_timestamp"])
        staleness_days = (reference_date - meas_ts).days
        latest_loco_agrees = str(last["LomNumber"]).strip().lower() == lom
        is_recently_measured = latest_loco_agrees and staleness_days <= RECENCY_THRESHOLD_DAYS
        # Backward-compatible alias: this is measurement recency, not a proven fit.
        is_current_fit = is_recently_measured

        row = {
            "wheelset_equipment_id": int(ws),
            "loco_number": loco_number,
            "locomotive_id": int(target.iloc[0]["locomotive_id"]),
            "latest_measurement": pd.Timestamp(last["measurement_timestamp"]).isoformat(),
            "latest_mean_wsmDia": _f(last["mean_wsmDia"]),
            "latest_mean_wsmFlange": _f(last["mean_wsmFlange"]),
            "latest_mean_wsmRoot": _f(last["mean_wsmRoot"]),
            "latest_mean_wsmThread": _f(last["mean_wsmThread"]),
            "days_since_turning": _f(last["days_since_turning"]),
            "distance_since_turning_km": _f(last["distance_since_turning_km"]),
            "n_turns": int((turns["wheelset_equipment_id"] == ws).sum()),
            "wheel_position_1_12": _f(last["wheel_position_1_12"]),
            "axle_position_1_6": _f(last["axle_position_1_6"]),
            "wheel_profile_2class": _f(last["wheel_profile_2class"]),
            "staleness_days": staleness_days,
            "latest_loco_agrees": latest_loco_agrees,
            "is_recently_measured": is_recently_measured,
            "is_current_fit": is_current_fit,
        }
        rows_all.append(row)
        if is_recently_measured:
            rows.append(row)
    
    s = seg[seg["wheelset_equipment_id"].isin(target["wheelset_equipment_id"])]
    axle_pos = target["axle_position_1_6"].dropna()
    n_expected_axles = int(axle_pos.max()) if not axle_pos.empty else None
    return {
        "loco_number": loco_number,
        "locomotive_id": int(target.iloc[0]["locomotive_id"]),
        "home_shed": str(target.iloc[-1]["home_shed"]) if pd.notna(target.iloc[-1]["home_shed"]) else None,
        "loco_type": str(target.iloc[0]["LocoType"]) if pd.notna(target.iloc[0]["LocoType"]) else None,
        "n_wheelsets": len(rows),
        "n_wheelsets_current": len(rows),
        "n_wheelsets_historical": len(rows_all) - len(rows),
        "n_expected_axles": n_expected_axles,
        "recency_threshold_days": RECENCY_THRESHOLD_DAYS,
        "n_segments": int(s[["wheelset_equipment_id", "segment_index"]].drop_duplicates().shape[0]) if not s.empty else 0,
        "n_turns": int(turns.shape[0]),
        "wheelsets": rows,
        "wheelsets_all": rows_all,
    }


def loco_wheelset_table(loco_number: str) -> dict:
    """Enhanced loco wheelset table (P2.3): current state + forecasts + P(turn)
    + limiting dimension per wheelset.

    The snapshot (one row per wheelset, current state) carries the degradation
    forecast, P(turn) and limiting dimension; we merge it back onto the live
    wheelset list so the table shows both identity and model output.
    """
    base = loco_summary(loco_number)
    snap = _snapshot_df()
    snap_loco = None
    if snap is not None and "loco_number" in snap.columns:
        snap_loco = snap[snap["loco_number"].astype(str).eq(str(loco_number))]

    rows = []
    rows_all = []
    for w in base["wheelsets_all"]:
        ws = w["wheelset_equipment_id"]
        row = dict(w)
        if snap_loco is not None:
            m = snap_loco[snap_loco["wheelset_equipment_id"] == ws]
            if not m.empty:
                r = m.iloc[0]
                row["limiting_dim"] = r["limiting_dim"] if pd.notna(r.get("limiting_dim")) else None
                row["limiting_reason"] = str(r["limiting_reason"]) if pd.notna(r.get("limiting_reason")) else None
                row["days_to_condemning_dia"] = _f(r.get("days_to_condemning_dia"))
                for h in (30, 60, 90):
                    row[f"pturn_{h}d"] = _f(r.get(f"pturn_{h}d"))
                    row[f"pturn_{h}d_calibrated"] = _f(r.get(f"pturn_{h}d_calibrated"))
                    row[f"pturn_{h}d_decile"] = _f(r.get(f"pturn_{h}d_decile"))
                for dim in WEAR_DIMS:
                    row[f"fc_{dim}_90d"] = _f(r.get(f"fc_{dim}_90d_pred"))
                row["wear_bands"] = _wear_watch_bands(r)
        rows_all.append(row)
        if w["is_recently_measured"]:
            rows.append(row)

    return {
        "loco_number": base["loco_number"],
        "locomotive_id": base["locomotive_id"],
        "home_shed": base["home_shed"],
        "loco_type": base["loco_type"],
        "n_wheelsets": len(rows),
        "n_wheelsets_current": len(rows),
        "n_wheelsets_historical": base.get("n_wheelsets_historical", 0),
        "n_expected_axles": base.get("n_expected_axles"),
        "recency_threshold_days": base.get("recency_threshold_days", 90),
        "n_segments": base["n_segments"],
        "n_turns": base["n_turns"],
        "wheelsets": rows,
        "wheelsets_all": rows_all,
        "snapshot_sourced": snap_loco is not None,
    }


def wheelset_history(wheelset_id: int) -> dict:
    wes = load_wes()
    w = wes[wes["wheelset_equipment_id"] == wheelset_id].sort_values("measurement_timestamp")
    if w.empty:
        return {"wheelset_equipment_id": wheelset_id, "measurements": [], "turns": []}
    out_m = []
    for _, r in w.iterrows():
        out_m.append({
            "measurement_timestamp": pd.Timestamp(r["measurement_timestamp"]).isoformat(),
            "mean_wsmDia": _f(r["mean_wsmDia"]),
            "mean_wsmFlange": _f(r["mean_wsmFlange"]),
            "mean_wsmRoot": _f(r["mean_wsmRoot"]),
            "mean_wsmThread": _f(r["mean_wsmThread"]),
            "mean_wsmFlangeThickness": _f(r["mean_wsmFlangeThickness"]),
            "mean_wsmWheelGauge": _f(r["mean_wsmWheelGauge"]),
            "segment_index": _f(r["seg_id"]),
            "turn_event": bool(r["turn_event"]),
            "replacement": bool(r["replacement"]),
            "days_since_turning": _f(r["days_since_turning"]),
        })
    turns = pd.read_parquet(TURNS)
    t = turns[turns["wheelset_equipment_id"] == wheelset_id].sort_values("post_ts")
    out_t = []
    for _, r in t.iterrows():
        out_t.append({
            "wheelset_equipment_id": wheelset_id,
            "pre_ts": pd.Timestamp(r["pre_ts"]).isoformat(),
            "post_ts": pd.Timestamp(r["post_ts"]).isoformat(),
            "pre_wsmDia": _f(r.get("pre_wsmDia")),
            "post_wsmDia": _f(r.get("post_wsmDia")),
            "delta_wsmDia": round(_f(r.get("delta_wsmDia")), 4) if pd.notna(r.get("delta_wsmDia")) else None,
            "pre_wsmFlange": _f(r.get("pre_wsmFlange")),
            "post_wsmFlange": _f(r.get("post_wsmFlange")),
            "segment_index": _f(r.get("segment_index")),
            "delta_wsmFlangeThickness": round(_f(r.get("delta_wsmFlangeThickness")), 4)
            if pd.notna(r.get("delta_wsmFlangeThickness")) else None,
            "dia_cut": _f(r.get("cut_dia")),
        })
    return {"wheelset_equipment_id": wheelset_id, "measurements": out_m, "turns": out_t}


def _f(v) -> float | None:
    try:
        x = float(v)
        return None if np.isnan(x) else round(x, 4)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# P1.1 fleet snapshot -> fleet overview / risk / search / shed endpoints
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _snapshot_df() -> pd.DataFrame | None:
    if not SNAPSHOT_PARQUET.exists():
        return None
    return pd.read_parquet(SNAPSHOT_PARQUET)


def _with_current_staleness(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Recalculate staleness against the wall clock (now - latest measurement).

    The snapshot file records staleness at build time; for the live product the
    honest view is "how old is this measurement relative to today", so fleet
    endpoints recompute it from latest_measurement on every request.
    """
    if df is None or "latest_measurement" not in df.columns:
        return df
    df = df.copy()
    ts = pd.to_datetime(df["latest_measurement"], errors="coerce")
    df["staleness_days"] = (pd.Timestamp.now() - ts).dt.days
    return df


def fleet_overview() -> dict:
    """Fleet KPI summary + distributions from the P1.1 snapshot (single row/wheelset)."""
    df = _with_current_staleness(_snapshot_df())
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    pturn_cols = [c for c in df.columns if c.startswith("pturn_")]
    wear_cols = [f"mean_{d}" for d in WEAR_DIMS]
    shed = (df.groupby("shed_any").size()
            .sort_values(ascending=False).head(10).rename("n_wheelsets").reset_index())
    return {
        "n_wheelsets": int(len(df)),
        "snapshot_built_at": _manifest_ts(),
        "model_version": _first_str(df, "model_version"),
        "train_cutoff": _first_str(df, "train_cutoff"),
        "staleness_days_median": _f(df["staleness_days"].median()) if "staleness_days" in df else None,
        "limiting_dim": {k: int(v) for k, v in df["limiting_dim"].value_counts(dropna=False).items()
                         if pd.notna(k)},
        "pturn_share_above_threshold_pct": {
            c.replace("pturn_", ""): round(float((df[c] >= 0.01).mean()) * 100, 2) for c in pturn_cols},
        "wear_distribution_mm": {
            c.replace("mean_", ""): {"q50": _f(df[c].quantile(0.5)), "q90": _f(df[c].quantile(0.9)),
                                     "q99": _f(df[c].quantile(0.99))} for c in wear_cols if c in df},
        "days_to_condemning_within_180d": int((df.get("days_to_condemning_dia", 0) <= 180).sum()),
        "feature_days_since_turning": {
            "q50": _f(df["days_since_turning"].quantile(0.5)) if "days_since_turning" in df else None,
            "q90": _f(df["days_since_turning"].quantile(0.9)) if "days_since_turning" in df else None},
        "top_sheds": shed.to_dict(orient="records"),
        "model_of_record_ranking": {
            "primary": "target_b_turn_90d_calibrated",
            "primary_label": "Calibrated P(turn) 90d (Phase 4 Target B)",
            "roots": ["flange", "root", "tread"],
            "secondary": "wear_margin_watch_bands (display only, never ranked)",
            "note": ("Target A (root > 6 mm) is quarantined as a diagnostic due to "
                     "data prevalence; Target B (turning) is the production ranking."),
        },
    }


def _wear_watch_bands(r) -> dict:
    """Wear-margin watch bands for one snapshot row (DISPLAY-only).

    For each wear dim (root/flange/tread) the band is how close the 90d
    predicted level sits to its approved Wrpld limit, relative to the limit
    range: `healthy` (>= WATCH_BAND_HEALTHY headroom), `watch`, or `near`
    (< WATCH_BAND_NEAR headroom). These are a UI colour convention and are
    NEVER a sorting key or a condemning threshold - the LIMIT_REGISTER limits
    stay authoritative. `headroom` = 1 - value/limit (clamped to >= 0).
    """
    bands = {}
    for dim, reg in LIMIT_REGISTER.items():
        if dim == "wsmDia" or reg.get("limit_mm") is None:
            continue
        limit = float(reg["limit_mm"])
        value = r.get(f"fc_{dim}_90d_pred")
        if value is None or not np.isfinite(value):
            value = r.get(f"mean_{dim}")
        if value is None or not np.isfinite(value):
            bands[dim] = {"band": "unknown", "headroom": None}
            continue
        headroom = max(0.0, 1.0 - float(value) / limit)
        if headroom >= WATCH_BAND_HEALTHY:
            band = "healthy"
        elif headroom >= WATCH_BAND_NEAR:
            band = "watch"
        else:
            band = "near"
        bands[dim] = {"band": band,
                      "headroom": round(headroom, 4),
                      "limit_mm": reg["limit_mm"]}
    return bands


def _rank_col(df: pd.DataFrame, sort_by: str) -> str:
    """Column actually used for ranking.

    The primary fleet ranking is the calibrated P(turn) (Phase 4 Target B,
    empirical realized rate), not the raw model score - the UI hands us the
    raw column and we promote to the calibrated twin when the snapshot has it.
    """
    cal = f"{sort_by}_calibrated"
    if sort_by.startswith("pturn_") and cal in df.columns and df[cal].notna().any():
        return cal
    return sort_by


def fleet_risk(shed: str | None = None, loco_type: str | None = None,
               limiting_dim: str | None = None, risk_level: str | None = None,
               sort_by: str = "pturn_90d", descending: bool = True,
               page: int = 1, page_size: int = 50,
               max_staleness_days: int | None = 365,
               days_to_condemning_max: int | None = None,
               pturn_min: float | None = None) -> dict:
    """Paginated, filterable, rankable wheelset risk table (P2.2 fleet view).

    `max_staleness_days` (default 365) hides wheelsets whose latest measurement
    is ancient. The risk table ranks "what to look at today"; a wheelset not
    measured in over a year is not evidence of a live fault. This is measurement
    recency, not proven equipment fit — pass max_staleness_days=None to show all.

    Action-queue filters: `days_to_condemning_max` keeps wheelsets within N days
    of the approved 1016 mm dia hard stop; `pturn_min` keeps wheelsets whose 90d
    P(turn) is at or above a fraction (e.g. 0.05 = 5%). Both are honest cuts on
    measurement signals, not guarantees of a turn.
    """
    df = _with_current_staleness(_snapshot_df())
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    if max_staleness_days is not None and "staleness_days" in df.columns:
        df = df[df["staleness_days"] <= max_staleness_days]
    if shed:
        df = df[df["shed_any"].astype(str).eq(shed)]
    if loco_type:
        df = df[df["loco_type"].astype(str).eq(loco_type)]
    if limiting_dim:
        df = df[df["limiting_dim"].astype(str).eq(limiting_dim)]
    if days_to_condemning_max is not None:
        df = df[df["days_to_condemning_dia"].notna() &
                (df["days_to_condemning_dia"] <= days_to_condemning_max)]
    if pturn_min is not None:
        cmp_col = "pturn_90d_calibrated" if "pturn_90d_calibrated" in df.columns else "pturn_90d"
        df = df[df[cmp_col].notna() & (df[cmp_col] >= pturn_min)]
    if risk_level:
        # risk_level: "pturn" | "condemning" | "wear" - each level is its own cut
        if risk_level == "pturn":
            cmp_col = "pturn_90d_calibrated" if "pturn_90d_calibrated" in df.columns else "pturn_90d"
            df = df[df[cmp_col] >= 0.01]
        elif risk_level == "condemning":
            df = df[df.get("days_to_condemning_dia", np.inf) <= 180]
        elif risk_level == "wear":
            df = df[df["limiting_dim"].isin(["wsmRoot", "wsmFlange", "wsmThread"])]

    rank_col = _rank_col(df, sort_by)
    if rank_col in df.columns and df[rank_col].notna().any():
        df = df.sort_values(rank_col, ascending=not descending, na_position="last")
    total = int(len(df))
    start = (page - 1) * page_size
    page_df = df.iloc[start:start + page_size]
    cols = ["wheelset_equipment_id", "loco_number", "shed_any", "loco_type",
            "limiting_dim", "limiting_reason", "days_to_condemning_dia",
            "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
            "feature_coverage", "staleness_days", "latest_measurement"]
    cols = [c for c in cols if c in page_df.columns]
    items = (page_df[cols].fillna(np.nan).replace({np.nan: None}).to_dict("records"))
    for item in items:
        lm = item.get("latest_measurement")
        if lm is not None:
            item["latest_measurement"] = str(lm) if isinstance(lm, (pd.Timestamp, str)) else lm
    pt_cols = [c for c in page_df.columns if c.startswith("pturn_")]
    for item, (_, r) in zip(items, page_df.iterrows()):
        for c in pt_cols:
            item[c] = _f(r[c])
        item["wear_bands"] = _wear_watch_bands(r)
    return {"total": total, "page": page, "page_size": page_size,
            "items": items, "columns": cols + pt_cols,
            "ranked_by": rank_col,
            "max_staleness_days": max_staleness_days,
            "days_to_condemning_max": days_to_condemning_max,
            "pturn_min": pturn_min}


def fleet_search(q: str) -> dict:
    """Search loco number / shed / loco type from the snapshot."""
    df = _snapshot_df()
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    qn = str(q).strip().lower()
    if not qn:
        return {"query": q, "items": []}
    masks = []
    if "loco_number" in df.columns:
        masks.append(df["loco_number"].astype(str).str.lower().str.contains(qn, na=False))
    if "shed_any" in df.columns:
        masks.append(df["shed_any"].astype(str).str.lower().str.contains(qn, na=False))
    if "loco_type" in df.columns:
        masks.append(df["loco_type"].astype(str).str.lower().str.contains(qn, na=False))
    hit = masks[0] if len(masks) == 1 else (masks[0] | pd.Series(False, index=df.index))
    for m in masks[1:]:
        hit |= m
    sub = df.loc[hit]
    items = []
    if "loco_number" in sub.columns:
        for lnum, grp in sub.groupby("loco_number"):
            items.append({"loco_number": lnum,
                          "shed": str(grp["shed_any"].iloc[0]) if "shed_any" in grp else None,
                          "loco_type": str(grp["loco_type"].iloc[0]) if "loco_type" in grp else None,
                          "n_wheelsets": int(len(grp))})
    return {"query": q, "total": int(len(items)), "items": items}


def shed_overview(shed: str) -> dict:
    """Shed-level aggregation from the snapshot."""
    df = _with_current_staleness(_snapshot_df())
    if df is None:
        return {"error": f"fleet snapshot not built: {SNAPSHOT_PARQUET.relative_to(ML_ROOT)}"}
    if "shed_any" not in df.columns:
        return {"shed": shed, "n_wheelsets": 0, "error": "snapshot has no shed_any column"}
    sub = df[df["shed_any"].astype(str).eq(str(shed))]
    if sub.empty:
        locos = df[df["loco_number"].astype(str).eq(str(shed))]
        if locos.empty:
            return {"shed": shed, "n_wheelsets": 0}
        sub = locos
    return {
        "shed": shed,
        "n_wheelsets": int(len(sub)),
        "n_locos": int(sub["loco_number"].nunique()) if "loco_number" in sub else 0,
        "limiting_dim": {k: int(v) for k, v in sub["limiting_dim"].value_counts(dropna=False).items()
                         if pd.notna(k)},
        "pturn_90d_mean_pct": round(float(sub["pturn_90d"].mean()) * 100, 2) if "pturn_90d" in sub else None,
        "pturn_90d_p90_pct": round(float(sub["pturn_90d"].quantile(0.9)) * 100, 2) if "pturn_90d" in sub else None,
        "days_to_condemning_within_180d": int((sub.get("days_to_condemning_dia", 0) <= 180).sum()),
        "staleness_days_median": _f(sub["staleness_days"].median()) if "staleness_days" in sub else None,
    }


def _first_str(df: pd.DataFrame, col: str) -> str | None:
    if col not in df.columns:
        return None
    v = df[col].dropna()
    return str(v.iloc[0]) if len(v) else None


def _manifest_ts() -> str | None:
    try:
        return json.loads(SNAPSHOT_MANIFEST.read_text()).get("built_at_utc")
    except Exception:
        return None