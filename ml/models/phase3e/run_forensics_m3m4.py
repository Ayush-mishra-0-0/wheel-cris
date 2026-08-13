"""Phase 3E - forensic M3-vs-M4 generalization study.

Research question: does OPERATIONAL CONTEXT provide TRANSFERABLE predictive
information beyond current state + trajectory + exposure?

Arms (feature splits mirror run_info_ladder):
  M3     = state + trajectory + distance history (as in the ladder)
  M4     = M3 + operational context: categoricals (home_shed, wheel profile,
           wheel/axle position, defect zone/division) + maintenance/RTIS counts
  M4none = M4 with the near-identity/high-cardinality group context removed
           (shed, wheel/axle position, defect zone/division), keeping only
           maintenance/RTIS activity counts as "operational"; proves the M3->M4
           delta is carried by group identity, not by count context.
  M4id   = M4 + wheelset_equipment_id (label-encoded EXACT identity). M4 as
           shipped does NOT contain this feature; M4id exists only to test the
           memorization hypothesis. Under loco-holdout the id encodes held-out
           wheelsets as -1 (unseen), so M4id's collapse there proves
           identity-only signal dies on unseen units.

Protocols (identical rows, splits, seeds; hyperparameters FIXED; no tuning):
  chrono     frozen chronological cohort (v3c split; fit = first 90% of train
             rows, cal = last 10%, eval on test rows) - same as info ladder
  locohold   stress test: ~20% of wheelset units fully held out (rng=SEED);
             fit train rows of held-IN units; eval on TEST rows of held-OUT
             units - THE transferability test (mirrors v3d run_loco_holdout)

Caveats we report rather than hide:
  - LocoType has ONE value (WAP7) in this corpus => no loco-type stratum.
  - No true loco-id column exists; wheelset_equipment_id is the finest
    loco-adjacent asset (16050 units; 364 units span >1 shed).
  - n and MAE ~SE (normal-approximation 95% CI) reported everywhere; cells
    with n < 50 are flagged and cannot move a conclusion.

Conformal: split-conformal widths on calibration rows; PLUS a calibration-set
multiplicative width recalibration (searches a factor on the CALIBRATION set
so its empirical coverage hits the nominal level; applied to test rows as a
diagnostic). This is the recheck requested for the under-covered WheelGauge
intervals.

No causal claim, no production horizon. All five bands reported.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from xgboost import XGBRegressor

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3c"))
sys.path.insert(0, str(_HERE.parent / "phase3d"))

from degradation_eval import (  # noqa: E402
    DIMENSIONS, STATE_COLUMNS, QUALITY_COLUMNS, CATEGORICAL_COLUMNS,
    ROW_ID_COL, add_targets_and_bases,
)

ROOT = Path(__file__).resolve().parents[2]
V3E = ROOT / "model_datasets" / "v3e" / "forecast_information_ladder.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3e"
SEED = 42
LEDGER_END = pd.Timestamp("2025-12-31")
HOLDOUT_FRAC = 0.20
CAL_TAIL_FRAC = 0.10
BANDS = ["30d", "60d", "90d", "180d", "365d"]
NOMINAL = {"i80": (0.80, 0.20), "i95": (0.95, 0.05)}
ID_COL = "wheelset_equipment_id"
TRAJ_WINDOWS = [30, 90, 180]
MAINTENANCE_COLS = [
    "maintenance_jobcard_creation_count", "rtis_source_event_count",
    "rtis_source_event_type_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
]
LIFECYCLE_COLS = ["days_since_turning", "wheel_age_days_proxy"]

XGB_HP = dict(n_estimators=250, max_depth=6, learning_rate=0.1,
              subsample=1.0, colsample_bytree=1.0,
              tree_method="hist", n_jobs=-1)


# --------------------------------------------------------------------------- #
# feature arms
# --------------------------------------------------------------------------- #
def traj_and_dist_cols() -> tuple[list[str], list[str]]:
    traj_rate, dist_hist = [], []
    for W in TRAJ_WINDOWS:
        traj_rate.append(f"inspection_count_{W}d")
        dist_hist += [f"km_last_{W}d", f"km_{W}d_available"]
        for d in DIMENSIONS:
            traj_rate += [f"{d}_change_last_{W}d",
                          f"{d}_rate_per_day_{W}d",
                          f"{d}_rate_per_1000km_{W}d"]
    traj_rate += ["days_since_last_inspection"]
    return traj_rate, dist_hist


def group_context_cols() -> list[str]:
    """Near-identity group context: which unit / shed / position family."""
    return ["home_shed", "wheel_profile_2class", "wheel_position_1_12",
            "axle_position_1_6", "defect_zone", "defect_division", "LocoType"]


def arm_sets() -> dict[str, list[str]]:
    state = (STATE_COLUMNS + [c + "_code" for c in QUALITY_COLUMNS]
             + ["interval_days", "horizon_days"] + LIFECYCLE_COLS)
    traj, dist = traj_and_dist_cols()
    counts = MAINTENANCE_COLS
    group = group_context_cols()
    m3 = sorted(state + traj + dist)
    m4 = sorted(state + traj + dist + group + counts)
    m4none = sorted(state + traj + dist + counts)   # M4 minus group context
    m4id = sorted(m4 + [ID_COL])
    return {"M3": m3, "M4": m4, "M4none": m4none, "M4id": m4id}


# --------------------------------------------------------------------------- #
# matrix / model plumbing
# --------------------------------------------------------------------------- #
def fit_cat_encoder(wear: pd.DataFrame) -> dict[str, dict]:
    enc = {}
    cols = list(set(CATEGORICAL_COLUMNS + [ID_COL]))
    for c in cols:
        if c in wear.columns:
            vals = sorted(wear[c].dropna().astype(str).unique())
            enc[c] = {v: i for i, v in enumerate(vals)}
    return enc


def prepare_matrix(wear: pd.DataFrame, num_cols: list[str],
                   cat_encoder: dict[str, dict] | None = None) -> np.ndarray:
    enc = wear.copy()
    qmap = {"MISSING": 0, "NOT_APPLICABLE": 1, "SEMANTICS_BLOCKED": 2,
            "IMPLAUSIBLE": 3, "OBSERVED_VALID": 4}
    for q in QUALITY_COLUMNS:
        enc[q + "_code"] = enc[q].fillna("MISSING").map(qmap).astype(float)
    enc[num_cols] = enc[num_cols].replace({pd.NA: np.nan, pd.NaT: np.nan})
    cats = [c for c in list(set(CATEGORICAL_COLUMNS + [ID_COL])) if c in num_cols]
    for c in cats:
        mp = (cat_encoder or {}).get(c, {})
        enc[c] = enc[c].astype(str).map(mp).astype(float).fillna(-1.0)
    M = enc[num_cols].astype(float).fillna(0.0)
    for c in [f"km_{W}d_available" for W in TRAJ_WINDOWS]:
        if c in M.columns:
            M[c] = M[c].clip(0, 1)
    return M.to_numpy().astype(np.float64)


def fit_xgb(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray, seed=SEED):
    ytr = np.asarray(ytr, dtype=float)
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return np.full(Xte.shape[0], np.nan)
    m = XGBRegressor(random_state=seed, **XGB_HP)
    m.fit(Xtr[fin], ytr[fin])
    return m, m.predict(Xte)


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def reg_metrics(yt: np.ndarray, yp: np.ndarray) -> dict:
    yt = np.asarray(yt, dtype=float)
    yf = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n < 10:
        return {"mae": np.nan, "mae_se": np.nan, "ci95_lo": np.nan,
                "ci95_hi": np.nan, "rmse": np.nan, "r2": np.nan,
                "spearman": np.nan, "n": n, "n_ok": n >= 50}
    yt, yf = yt[v], yf[v]
    err = np.abs(yt - yf)
    mae = float(np.mean(err))
    se = float(np.std(err, ddof=1) / np.sqrt(n))
    sign = None
    return {"mae": round(mae, 4), "mae_se": round(se, 4),
            "ci95_lo": round(mae - 1.96 * se, 4), "ci95_hi": round(mae + 1.96 * se, 4),
            "rmse": round(float(np.sqrt(np.mean((yt - yf) ** 2))), 4),
            "r2": round(1 - float(np.sum((yt - yf) ** 2) / np.sum((yt - yt.mean()) ** 2)), 4)
            if np.sum((yt - yt.mean()) ** 2) > 0 else np.nan,
            "spearman": round(float(spearmanr(yt, yf)[0]), 4)
            if not np.all(yf == yf[0]) else np.nan,
            "n": n, "n_ok": n >= 50}


def conformal_bound(resid: np.ndarray, alpha: float) -> float | None:
    s = np.asarray(resid, dtype=float)
    s = s[np.isfinite(s)]
    if s.size < 10:
        return None
    k = int(np.ceil((s.size + 1) * (1.0 - alpha)))
    k = min(max(k, 1), s.size)
    return float(np.partition(s, k - 1)[k - 1])


def coverage_matching_mult(cal_resid: np.ndarray, alpha: float) -> float | None:
    """Multiplier such that, ON THE CALIBRATION SET, coverage of |r|<=w*mult
    equals 1-alpha (calibration-level recalibration; touches only cal rows,
    never the model or test rows)."""
    s = np.asarray(cal_resid, dtype=float)
    s = s[np.isfinite(s)]
    if s.size < 20:
        return None
    base = conformal_bound(s, alpha)
    if base is None or base <= 0:
        return None
    target = 1.0 - alpha
    lo, hi = 0.02, 8.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        cov = float(np.mean(s <= base * mid))
        if cov < target:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 3)


def coverage_cell(yt: np.ndarray, yp: np.ndarray, width: float | None,
                  cal_mult: float | None) -> dict:
    yt = np.asarray(yt, dtype=float)
    yp = np.asarray(yp, dtype=float)
    v = np.isfinite(yt) & np.isfinite(yp)
    n = int(v.sum())
    if n == 0:
        return {"n": 0}
    if width is None or n < 10:
        return {"n": n, "coverage": None, "width": None}
    w = width if cal_mult is None else width * cal_mult
    hit = int(np.sum(np.abs(yt[v] - yp[v]) <= w))
    return {"n": n, "coverage": round(hit / n, 4), "width": round(float(w), 4),
            "cal_mult": None if cal_mult is None else round(float(cal_mult), 3)}


# --------------------------------------------------------------------------- #
# splits
# --------------------------------------------------------------------------- #
def build_masks(wes: pd.DataFrame, protocol: str):
    """Return (fit_idx, cal_idx, ev_idx, ev_band, ev_time) for a protocol."""
    tr_mask = wes["split"].eq("train").to_numpy()
    te_mask = wes["split"].eq("test").to_numpy()
    if protocol == "chrono":
        tr_pos = np.where(tr_mask)[0]
        cal_from = int(len(tr_pos) * (1.0 - CAL_TAIL_FRAC))
        fit = tr_pos[:cal_from]
        cal = tr_pos[cal_from:]
        ev = np.where(te_mask)[0]
    elif protocol == "locohold":
        rng = np.random.default_rng(SEED)
        units = np.sort(wes[ID_COL].unique())
        n_hold = int(len(units) * HOLDOUT_FRAC)
        held = set(rng.choice(units, size=n_hold, replace=False))
        ho = wes[ID_COL].isin(held).to_numpy()
        pos = np.where(tr_mask & ~ho)[0]
        cal_from = int(len(pos) * (1.0 - CAL_TAIL_FRAC))
        fit = pos[:cal_from]
        cal = pos[cal_from:]
        ev = np.where(te_mask & ho)[0]
    else:
        raise ValueError(protocol)
    band = wes["horizon_window"].to_numpy()[ev]
    return fit, cal, ev, band


def _splits_of(wes):
    pass


def permute_importance(model, X, y, feats: list[str], rng) -> dict:
    """Permutation importance on an eval matrix; returns dict feat -> delta MAE
    (higher = greater impact of shuffling that feature)."""
    m = np.abs(y - model.predict(X)).mean()
    out = {}
    Xp = X.copy()
    for j, f in enumerate(feats):
        col = Xp[:, j]
        perm = rng.permutation(col)
        Xp[:, j] = perm
        d = np.abs(y - model.predict(Xp)).mean() - m
        Xp[:, j] = col
        out[f] = round(float(d), 4)
    return out


def main() -> None:
    wes = pd.read_parquet(V3E)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)

    arms = arm_sets()
    cat_encoders = fit_cat_encoder(wes)

    out = {
        "task": "forensic M3-vs-M4 generalization study (Stage 3E)",
        "status": "diagnostic; no causal claims; no production horizon chosen",
        "seed": SEED, "bands": BANDS, "arms": list(arms.keys()),
        "n_lock": "LocoType single value (WAP7) -> no loco-type stratum exists",
        "identity": (f"no true loco-id column; {ID_COL} used as finest loco "
                     f"asset ({int(wes[ID_COL].nunique())} units, "
                     f"{int((wes.groupby(ID_COL)['home_shed'].nunique()>1).sum())} "
                     f"span >1 shed)"),
        "results": {}, "recalibration": {}, "importance": {}, "strata": {},
    }

    rng = np.random.default_rng(SEED)
    chrono_key = set()

    for protocol in ["chrono", "locohold"]:
        fit, cal, ev, band_ev = build_masks(wes, protocol)
        pro = out["results"][protocol] = {"n_fit": int(len(fit)),
                                          "n_cal": int(len(cal)),
                                          "n_ev": int(len(ev))}
        preds = {}
        preds_ev = preds
        for arm, cols in arms.items():
            Xf = prepare_matrix(wes.loc[fit], cols, cat_encoders)
            Xc = prepare_matrix(wes.loc[cal], cols, cat_encoders)
            Xe = prepare_matrix(wes.loc[ev], cols, cat_encoders)
            for d in DIMENSIONS:
                yf = wes.loc[fit, f"target_{d}"].to_numpy(dtype=float)
                m, p_cal = fit_xgb(Xf, yf, Xc)
                _, p_ev = fit_xgb(Xf, yf, Xe)
                preds_ev[(arm, d)] = p_ev
                res_cal = np.abs(wes.loc[cal, f"target_{d}"].to_numpy(dtype=float) - p_cal)

                key = f"{protocol}/{arm}/{d}"
                pro[key] = {}
                yt = wes.loc[ev, f"target_{d}"].to_numpy(dtype=float)
                cal_band = wes.loc[cal, "horizon_window"].to_numpy()
                for band in BANDS:
                    bm = band_ev == band
                    cell = reg_metrics(yt[bm], p_ev[bm])
                    cb = cal_band == band
                    for lev, (cov, alpha) in NOMINAL.items():
                        w = conformal_bound(res_cal[cb], alpha)
                        mult = coverage_matching_mult(res_cal[cb], alpha)
                        cell[lev] = coverage_cell(yt[bm], p_ev[bm], w, mult)
                        cell[lev + "_raw"] = coverage_cell(yt[bm], p_ev[bm], w, None)
                    pro[key][band] = cell
        for band in BANDS:
                    bm = band_ev == band
                    cell = reg_metrics(yt[bm], p_ev[bm])
                    cb = cal_band == band
                    for lev, (cov, alpha) in NOMINAL.items():
                        w = conformal_bound(res_cal[cb], alpha)
                        mult = coverage_matching_mult(res_cal[cb], alpha)
                        cell[lev] = coverage_cell(yt[bm], p_ev[bm], w, mult)
                        cell[lev + "_raw"] = coverage_cell(yt[bm], p_ev[bm], w, None)
                    pro[key][band] = cell
        if protocol == "chrono":
            chrono_preds = dict(preds_ev)
            chrono_ev = np.array(ev)

    # recalibration summary (M4, chrono + locohold) per dim/band
    for protocol in ("chrono", "locohold"):
        pro = out["results"][protocol]
        for d in DIMENSIONS:
            for band in BANDS:
                key = f"{protocol}/M4/{d}"
                if key in pro and band in pro[key]:
                    cell = pro[key][band]
                    out["recalibration"].setdefault(f"{protocol}/{d}/{band}", {})
                    for lev in ("i80", "i95"):
                        out["recalibration"][f"{protocol}/{d}/{band}"][lev] = {
                            "raw": cell[lev + "_raw"]["coverage"],
                            "recal": cell[lev]["coverage"],
                            "cal_mult": cell[lev]["cal_mult"],
                            "width_raw": cell[lev + "_raw"]["width"],
                            "width_rec": cell[lev]["width"],
                            "n": cell["n"],
                        }

    # permutation importance on chrono M4 (test rows), all dims
    fit, cal, ev, _ = build_masks(wes, "chrono")
    cols = arms["M4"]
    Xf = prepare_matrix(wes.loc[fit], cols, cat_encoders)
    Xe = prepare_matrix(wes.loc[ev], cols, cat_encoders)
    for d in DIMENSIONS:
        yf = wes.loc[fit, f"target_{d}"].to_numpy(dtype=float)
        yt = wes.loc[ev, f"target_{d}"].to_numpy(dtype=float)
        m, _ = fit_xgb(Xf, yf, Xe)
        imp = permute_importance(m, Xe, yt, cols, rng)
        out["importance"][d] = dict(
            sorted(imp.items(), key=lambda kv: -kv[1]))
        out["importance"][d + "_baseline_mae"] = round(
            float(np.nanmean(np.abs(yt - m.predict(Xe)))), 4)

    # stratification chrono: M3 vs M4 MAE delta, wsmDia on test rows, by group
    yt_dia = wes.loc[ev, "target_wsmDia"].to_numpy(dtype=float)
    for group_col in ["home_shed", "wheel_position_1_12", "axle_position_1_6",
                      "defect_zone", "wheel_profile_2class"]:
        g = wes.loc[ev, group_col].astype(str)
        strata = {}
        for val in sorted(g.unique(), key=str):
            sel = (g == val).to_numpy()
            n = int(sel.sum())
            if n < 1:
                continue
            mae3 = reg_metrics(yt_dia[sel], chrono_preds[("M3", "wsmDia")][sel])["mae"]
            mae4 = reg_metrics(yt_dia[sel], chrono_preds[("M4", "wsmDia")][sel])["mae"]
            strata[str(val)] = {"n": n, "n_ok": n >= 50,
                                "mae3": mae3, "mae4": mae4,
                                "delta_mae_3to4": round(float(mae4 - mae3), 4)}
        out["strata"][group_col] = strata

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "forensics_m3m4.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("M3M4 forensics ->", OUTPUT.relative_to(ROOT))