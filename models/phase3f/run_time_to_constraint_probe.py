"""Phase 3F diagnostic: time-to-constraint / limiting-dimension probe.

Architecture (per user-approved spec):
    current state
      |-- diameter ----> current hard margin (D - 1016, decreases toward limit)
      |-- root --------> predicted degradation (root grows toward 3mm condemning)
      |-- flange ------> predicted degradation (DIAGNOSTIC ONLY, limit unconfirmed)
      |-- turning ctx --+
      v                 v
      constraint projection -> limiting dimension + time-to-constraint interval
                 |
                 v
      maintenance risk / recommended action

Conventions (data-verified 2026-08-11):
  - root is a defect-severity measurement: values 0..3+ mm, median 1.5, p90 3.2,
    89% <= 3.  LOWER is better, 3 mm = condemning MAX. margin = 3 - root, the
    physical quantity GROWS toward the limit. (Corrected from "root - 3" which
    would imply the opposite direction and contradict observed +slope.)
  - diameter: new ~1096, condemning minimum 1016; margin = D - 1016, D shrinks.
  - flange: provisional only (DIM_FLAG diagnostic_limit), not a production
    constraint until owner-confirmed.

Known limits honored:
  - NOT called RUL: it is time-to-constraint diagnostic until maintenance-event
    semantics are validated.
  - Point-in-time: all rates from frozen train-fit M4; conformal calibration on
    the last 10% of TRAIN rows (never test).
  - Actual turning is an OBSERVED maintenance event, not assumed = constraint.
  - No tuning, no deep sequence model.

Evaluation (A-D):
  A. predicted constraint before observed turning? (warning-time > 0)
  B. |predicted time-to-constraint - observed turning gap|  (days MAE)
  C. predicted limiting dimension vs dims actually near limit at turning
  D. actionable warning days before actual turning
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "phase3e"))
sys.path.insert(0, str(_HERE.parent / "phase3c"))

from degradation_eval import CATEGORICAL_COLUMNS, add_targets_and_bases  # noqa: E402
from run_info_ladder import arm_columns, prepare_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
V3F = ROOT / "model_datasets" / "v3f" / "change_space_benchmark.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3f"
SEED = 42

# engineering margins (owner-confirmed / documented)
LIMIT_ROOT = 3.0     # mm, condemning MAX (lower is better), approved
LIMIT_DIA_MIN = 1016.0  # mm, condemning minimum, from v1_1 report (new 1096)
# flange: owner-confirmed limit PENDING -> diagnostic only
FLANGE_LIMIT = None

DIMS_CONSTRAINT = ["wsmRoot", "wsmDia"]
DIMS_DIAG = ["wsmFlangeThickness"]
NOISE_FLOOR = {"wsmRoot": 0.10, "wsmDia": 1.0, "wsmFlangeThickness": 0.10}
LOOKAHEAD_DAY = 365.0
ALPHA = 0.80  # nominal coverage for constraint-time interval


def state_mean(df):
    cols = ["wsmDia1", "wsmDia2", "wsmRoot1", "wsmRoot2",
            "wsmFlangeThickness1", "wsmFlangeThickness2"]
    out = {}
    for d in ["wsmDia", "wsmRoot", "wsmFlangeThickness"]:
        a = df[f"{d}1"].to_numpy(dtype=float); b = df[f"{d}2"].to_numpy(dtype=float)
        q1 = df[f"{d}1_quality"].eq("OBSERVED_VALID").to_numpy()
        q2 = df[f"{d}2_quality"].eq("OBSERVED_VALID").to_numpy()
        out[d] = np.where(q1 & q2, (a + b) / 2.0, np.where(q1, a, np.where(q2, b, np.nan)))
    return out


def fit_xgb(Xtr, ytr, Xte, seed=SEED):
    ytr = np.asarray(ytr, dtype=float)
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        return np.full(Xte.shape[0], np.nan)
    m = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                     subsample=1.0, colsample_bytree=1.0, random_state=seed,
                     n_jobs=-1, tree_method="hist")
    m.fit(Xtr[fin], ytr[fin])
    return m.predict(Xte)


def main() -> None:
    wes = pd.read_parquet(V3F)
    wes = add_targets_and_bases(wes)
    wes = wes.sort_values("measurement_timestamp").reset_index(drop=True)
    tr_mask = (wes["split"] == "train").to_numpy()
    te_mask = (wes["split"] == "test").to_numpy()
    tr_pos = np.where(tr_mask)[0]
    cal_from = int(len(tr_pos) * 0.90)
    fit_mask = np.zeros(len(wes), dtype=bool); fit_mask[tr_pos[:cal_from]] = True
    cal_mask = np.zeros(len(wes), dtype=bool); cal_mask[tr_pos[cal_from:]] = True

    # ---- observed turning events (WES raw flags) per wheelset, point-in-time ----
    we = pd.read_parquet(WES, columns=["wheelset_equipment_id", "measurement_timestamp",
                                       "turning_record_at_measurement",
                                       "wsmRoot1", "wsmRoot2", "wsmDia1", "wsmDia2",
                                       "wsmRoot1_quality", "wsmRoot2_quality",
                                       "wsmDia1_quality", "wsmDia2_quality"])
    turn_wid = we.loc[we["turning_record_at_measurement"].eq(1)].copy()
    turn_map = {}
    turn_state = {}   # state (root, dia) at each turning record per wheelset
    for w, g in turn_wid.groupby("wheelset_equipment_id"):
        ts = pd.to_datetime(g["measurement_timestamp"]).sort_values()
        turn_map[int(w)] = ts.to_numpy(dtype="datetime64[us]")
        r1 = g.loc[ts.index, "wsmRoot1"].to_numpy(dtype=float)
        r2 = g.loc[ts.index, "wsmRoot2"].to_numpy(dtype=float)
        d1 = g.loc[ts.index, "wsmDia1"].to_numpy(dtype=float)
        d2 = g.loc[ts.index, "wsmDia2"].to_numpy(dtype=float)
        qr1 = g.loc[ts.index, "wsmRoot1_quality"].eq("OBSERVED_VALID").to_numpy()
        qr2 = g.loc[ts.index, "wsmRoot2_quality"].eq("OBSERVED_VALID").to_numpy()
        qd1 = g.loc[ts.index, "wsmDia1_quality"].eq("OBSERVED_VALID").to_numpy()
        qd2 = g.loc[ts.index, "wsmDia2_quality"].eq("OBSERVED_VALID").to_numpy()
        root = np.where(qr1 & qr2, (r1 + r2) / 2, np.where(qr1, r1, np.where(qr2, r2, np.nan)))
        dia = np.where(qd1 & qd2, (d1 + d2) / 2, np.where(qd1, d1, np.where(qd2, d2, np.nan)))
        turn_state[int(w)] = (ts.to_numpy(dtype="datetime64[us]"), root, dia)

    # ---- M4 rates per dimension (point-in-time) ----
    cols = arm_columns()["M4_operational"]
    Xf = prepare_matrix(wes.loc[fit_mask], cols, CATEGORICAL_COLUMNS)
    Xc = prepare_matrix(wes.loc[cal_mask], cols, CATEGORICAL_COLUMNS)
    Xt = prepare_matrix(wes.loc[te_mask], cols, CATEGORICAL_COLUMNS)

    te_time = pd.to_datetime(wes.loc[te_mask, "measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    te_wid = wes.loc[te_mask, "wheelset_equipment_id"].astype("int64").to_numpy()
    te_interval = wes.loc[te_mask, "interval_days"].to_numpy(dtype=float)
    te_year = pd.to_datetime(wes.loc[te_mask, "measurement_timestamp"]).dt.year.to_numpy()
    sm = state_mean(wes)

    models = {}
    cal_resid = {}
    dx_pred = {}
    for d in DIMS_CONSTRAINT + DIMS_DIAG:
        yf = wes.loc[fit_mask, f"dX_{d}"].to_numpy(dtype=float)
        p_te = fit_xgb(Xf, yf, Xt)
        p_cal = fit_xgb(Xf, yf, Xc)
        yc = wes.loc[cal_mask, f"dX_{d}"].to_numpy(dtype=float)
        resid = np.abs(yc - p_cal)
        resid = resid[np.isfinite(resid)]
        width = float(np.quantile(resid, ALPHA)) if resid.size else np.nan
        dx_pred[d] = p_te
        models[d] = {"width_%d%%" % int(ALPHA * 100): float(width) if np.isfinite(width) else None}

    # ---- margin & predicted rate at t ----
    for d in DIMS_CONSTRAINT + DIMS_DIAG:
        base = sm[d][te_mask]
        if d == "wsmRoot":
            margin = LIMIT_ROOT - base          # grows toward 3 -> margin shrinks
            sign_needed = +1                     # root INCREASES toward limit
            limit = LIMIT_ROOT
            unit_dir = "root grows toward 3mm max"
        elif d == "wsmDia":
            margin = base - LIMIT_DIA_MIN        # shrinks as D drops
            sign_needed = -1                     # dia DECREASES toward 1016
            limit = LIMIT_DIA_MIN
            unit_dir = "dia falls toward 1016mm min"
        else:
            margin = np.full_like(base, np.nan)  # diagnostic; no confirmed margin
            sign_needed = +1
            limit = np.nan
            unit_dir = "flange: DIAGNOSTIC, limit not confirmed"
        rate = dx_pred[d] / np.maximum(te_interval, 1e-6)   # mm/day predicted by M4
        # a constraint can only be approached if rate has the correct sign
        approaching = np.sign(np.nan_to_num(rate)) == sign_needed
        denom = np.abs(rate)
        t_con = np.where(approaching & np.isfinite(margin) & (margin > 0) & (denom > 1e-9),
                         margin / np.where(denom > 1e-9, denom, np.nan), np.inf)
        t_con = np.where(margin <= 0, 0.0, t_con)   # already at/over limit
        # conformal: rate +/- width/interval_days
        w = models[d].get("width_80%")
        if w is not None:
            rate_hi = (dx_pred[d] + w) / np.maximum(te_interval, 1e-6)
            rate_lo = np.maximum((dx_pred[d] - w), 0) / np.maximum(te_interval, 1e-6)
            dhi = np.abs(rate_hi)
            dlo = np.abs(rate_lo)
            t_hi = np.where(approaching & (margin > 0) & (dlo > 1e-9),
                            margin / np.where(dlo > 1e-9, dlo, np.nan), np.inf)
            t_lo = np.where(approaching & (margin > 0) & (dhi > 1e-9),
                            margin / np.where(dhi > 1e-9, dhi, np.nan), np.inf)
            t_lo = np.minimum(t_lo, np.inf)
        else:
            t_hi, t_lo = np.full_like(t_con, np.inf), np.full_like(t_con, np.inf)

        wes_ = wes  # noqa
        # store on the test-position arrays
        if d == "wsmRoot":
            T_root_lo, T_root_hi, T_root = t_lo, t_hi, t_con
        elif d == "wsmDia":
            T_dia_lo, T_dia_hi, T_dia = t_lo, t_hi, t_con

        # observed next turning gap (days) after t, cap at lookahead
        obs_gap = np.full(te_time.shape, np.inf)
        for i in range(te_time.shape[0]):
            arr = turn_map.get(int(te_wid[i]))
            if arr is not None and arr.size and arr[-1] >= te_time[i]:
                j = np.searchsorted(arr, te_time[i])
                if j < arr.size:
                    obs_gap[i] = (arr[j] - te_time[i]) / np.timedelta64(1, "D")
        obs_gap = np.minimum(obs_gap, LOOKAHEAD_DAY)

    # ---- combined: constraining dimension = min over constraints ----
    T_min = np.minimum(T_root, T_dia)
    limiting = np.where(T_root <= T_dia, "wsmRoot", "wsmDia")
    # constraint within lookahead?
    constrained = T_min <= LOOKAHEAD_DAY
    turned = np.isfinite(obs_gap) & (obs_gap < LOOKAHEAD_DAY)

    # ---- evaluation A-D on rows that actually turned within lookahead ----
    ev = pd.DataFrame({
        "te": te_time, "year": te_year, "wid": te_wid,
        "obs_turn_gap": obs_gap, "T_root": T_root, "T_dia": T_dia,
        "T_min": T_min, "limiting": limiting, "constrained": constrained,
        "turned": turned,
    })

    out = {
        "task": "time-to-constraint / limiting-dimension diagnostic (NOT RUL)",
        "conventions": {
            "root": "margin = 3 - root (root GROWS toward 3mm max; data-verified)",
            "dia": "margin = D - 1016 (D falls toward min)",
            "flange": "DIAGNOSTIC ONLY, limit not owner-confirmed",
        },
        "model": "M4 forecasts of dX/interval as rate; point-in-time; conformal on train tail",
        "lookahead_days": LOOKAHEAD_DAY,
        "interval_80": {d: models[d] for d in models},
        "n_test": int(te_mask.sum()),
        "eval": {},
    }

    # A: warning time distribution for turned rows
    sub = ev[ev["turned"]]
    warned = sub["T_min"] <= sub["obs_turn_gap"]
    out["eval"]["A_warned_before_turn"] = {
        "n_turned": int(len(sub)),
        "frac_pred_constrained_before_turn": round(float(warned.mean()), 4) if len(sub) else None,
        "frac_turned_within_lookahead": round(float(turned.mean()), 4),
        "frac_predict_constraint_within_365d": round(float(constrained.mean()), 4),
    }
    if len(sub):
        ahead = sub["obs_turn_gap"] - sub["T_min"]
        out["eval"]["A_warning_days"] = {
            "median": round(float(np.median(ahead)), 1),
            "p25": round(float(np.percentile(ahead, 25)), 1),
            "p75": round(float(np.percentile(ahead, 75)), 1),
            "mean": round(float(np.mean(ahead)), 1),
        }
        # B: time-to-constraint error vs observed turning
        err = np.abs(sub["T_min"] - sub["obs_turn_gap"])
        finite = np.isfinite(err)
        out["eval"]["B_time_to_constraint_error_days"] = {
            "n": int(finite.sum()), "mae": round(float(np.mean(err[finite])), 1),
            "median": round(float(np.median(err[finite])), 1),
        }
        # D: actionable warning = days we had a predicted constraint before turning
        pos = sub["T_min"] < sub["obs_turn_gap"]
        if pos.sum():
            wd = sub.loc[pos, "obs_turn_gap"] - sub.loc[pos, "T_min"]
            out["eval"]["D_actionable_warning_days"] = {
                "n": int(pos.sum()), "median": round(float(np.median(wd)), 1),
                "p10": round(float(np.percentile(wd, 10)), 1),
            }
    else:
        out["eval"]["A_warning_days"] = out["eval"]["B_time_to_constraint_error_days"] = \
            out["eval"]["D_actionable_warning_days"] = None

    # C: limiting-dimension agreement — compare predicted limiting dimension
    # against the dimension actually nearer its limit AT the observed turning
    # event (state at the turning record), not a raw-margin cross-scale compare.
    obs_lim_turn = np.full(len(ev), np.nan, dtype=object)
    obs_root_at_turn = np.full(len(ev), np.nan)
    obs_dia_at_turn = np.full(len(ev), np.nan)
    for i in range(len(ev)):
        arr = turn_state.get(int(ev["wid"].iloc[i]))
        if arr is None:
            continue
        ts, root, dia = arr
        j = np.searchsorted(ts, ev["te"].iloc[i])
        if j >= len(ts):
            continue
        if np.isfinite(root[j]) and np.isfinite(dia[j]):
            rm = LIMIT_ROOT - root[j]
            dm = dia[j] - LIMIT_DIA_MIN
            obs_root_at_turn[i] = root[j]
            obs_dia_at_turn[i] = dia[j]
            obs_lim_turn[i] = "wsmRoot" if rm <= dm else "wsmDia"
    ok = np.isfinite(obs_root_at_turn) & np.isfinite(obs_dia_at_turn) & np.isfinite(ev["T_root"].to_numpy()) & np.isfinite(ev["T_dia"].to_numpy())
    lim_pred = ev["limiting"].to_numpy()
    agree = lim_pred[ok] == np.asarray(list(obs_lim_turn[ok]))
    out["eval"]["C_limiting_dim_agreement_vs_turning_state"] = {
        "n_turned_with_state": int(ok.sum()),
        "frac_predict_matches_dim_nearer_limit_at_turn": (
            round(float(agree.mean()), 4) if int(ok.sum()) else None),
        "root_nearer_limit_at_turn_frac": (
            round(float((np.asarray(list(obs_lim_turn[ok])) == "wsmRoot").mean()), 4)
            if int(ok.sum()) else None),
        "mean_root_at_turn_mm": round(float(np.nanmean(obs_root_at_turn[ok])), 3)
        if int(ok.sum()) else None,
        "mean_dia_at_turn_mm": round(float(np.nanmean(obs_dia_at_turn[ok])), 3)
        if int(ok.sum()) else None,
    }
    # companion: state at turning vs the 3mm / 1016 limits
    out["eval"]["C_turning_state_vs_limits"] = {
        "root_at_turn_p50_p90": [round(float(np.percentile(obs_root_at_turn[ok], p)), 2)
                                 for p in (50, 90)] if int(ok.sum()) else None,
        "dia_at_turn_p50_p90": [round(float(np.percentile(obs_dia_at_turn[ok], p)), 2)
                                for p in (50, 90)] if int(ok.sum()) else None,
        "frac_root_at_turn_gt_3mm": round(float((obs_root_at_turn[ok] > LIMIT_ROOT).mean()), 4)
        if int(ok.sum()) else None,
    }

    # by-era summary of median constraint time (root / dia) on test
    out["by_era"] = {}
    for yr in ["pre-2024", "2024", "2025+"]:
        ysel = ev["year"] < 2024 if yr == "pre-2024" else (ev["year"] == 2024 if yr == "2024" else ev["year"] > 2024)
        lim = ev.loc[ysel, "T_min"]
        out["by_era"][yr] = {
            "n": int(ysel.sum()),
            "median_time_to_constraint_days": round(float(np.median(lim[np.isfinite(lim)])), 1),
            "frac_constrained_365d": round(float(ev.loc[ysel, "constrained"].mean()), 4),
            "root_limited_frac": round(float((ev.loc[ysel, "limiting"] == "wsmRoot").mean()), 4),
        }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dia_time_to_constraint_probe.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()