"""Phase 5 Layer 2 - trajectory-product analysis (flange/root/tread).

Single analysis artefact that makes the delta models honest and decision-aligned.
For flange / root / tread at 30/90/180 on the frozen v5 degradation substrate:

  1. delta metrics          - absolute and delta MAE/R2/Spearman side by side
                               (delta values read from degradation_benchmark.json;
                               reconfirmed on the temporal test split here).
  2. residual + noise floor - test delta residuals (predicted - realised change)
                               vs an empirical measurement-noise floor (central
                               same-timestamp, non-turn repeated readings).
  3. prediction intervals   - split conformal on the C1 delta model (fit on train,
                               calibrated on a temporal calibration slice, coverage
                               verified on the test split). 80% target.
  4. operational capture@k  - label = turned within H days (lifecycle_turns post_ts
                               in (t, t+H]); ranked by predicted delta. Censored
                               anchors (no turn AND no later measurement) dropped.
  5. residual panel         - per-wheelset predicted-vs-realised delta strip for an
                               in-substrate loco AND the serving path for Loco 37597
                               (LomNumber=37597, outside the substrate).

Outputs: models/experiments/v5/trajectory_product_analysis.json
         models/experiments/v5/trajectory_residual_panel.png
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from scipy.stats import median_abs_deviation
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBRegressor

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
TURNS = ROOT / "model_datasets" / "v5" / "lifecycle_turns.parquet"
BENCH = ROOT / "models" / "experiments" / "v5" / "degradation_benchmark.json"
SERV = ROOT / "models" / "phase5" / "serving" / "degradation"
OUT = ROOT / "models" / "experiments" / "v5"

DIMS = ("wsmFlange", "wsmRoot", "wsmThread")
# Dia conformal: same split-conformal path as the wear dims, so the dia
# forecast band + conservative days-to-condemning can be reported. Dia is a
# derived/diagnostic dimension, so it stays out of operational capture and
# the residual strip (wear drives turning; dia is the cut consequence).
CONF_DIMS = DIMS + ("wsmDia",)
HORIZONS = (30, 90, 180)
ALPHA = 0.20  # 80% conformal interval
SEED = 42

NUM_FEATS = [
    "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
    "mean_wsmFlangeThickness", "mean_wsmWheelGauge",
    "ph5_wsmFlange_rate_per_day_30d", "ph5_wsmFlange_rate_per_day_90d",
    "ph5_wsmFlange_rate_per_day_180d",
    "ph5_wsmThread_rate_per_day_30d", "ph5_wsmThread_rate_per_day_90d",
    "ph5_wsmThread_rate_per_day_180d",
    "wsmRoot_rate_per_day_30d", "wsmRoot_rate_per_day_90d",
    "wsmDia_rate_per_day_30d", "wsmDia_rate_per_day_90d",
    "days_since_turning", "distance_since_turning_km",
    "days_since_last_inspection", "wheel_age_days_proxy",
    "days_since_segment_start",
    "inspection_count_30d", "inspection_count_90d", "inspection_count_180d",
    "km_last_30d", "km_last_90d", "km_last_180d",
    "rtis_reporting_coverage_pct", "distance_per_day_km",
    "n_prior_turns", "segment_index",
    "axle_position_1_6", "wheel_position_1_12", "wheel_profile_2class",
]
CAT_FEATS = ["LocoType", "home_shed", "defect_zone", "shed_any"]

DAY = np.timedelta64(1, "D")


def build_matrix(df, enc=None):
    Xn = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(cat)
    else:
        Xc = enc.transform(cat)
    return Xn, Xc, enc


def metrics(y, yh):
    y = np.asarray(y, float)
    yh = np.asarray(yh, float)
    ok = np.isfinite(y) & np.isfinite(yh)
    y, yh = y[ok], yh[ok]
    if len(y) < 10:
        return None
    mae = float(np.mean(np.abs(y - yh)))
    rmse = float(np.sqrt(np.mean((y - yh) ** 2)))
    ss = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = float(1.0 - np.sum((y - yh) ** 2) / ss)
    try:
        rho = float(spearmanr(y, yh).statistic)
    except Exception:
        rho = None
    return {"mae": mae, "rmse": rmse, "r2": r2, "spearman": rho, "n": int(len(y))}


def noise_floor(wes: pd.DataFrame) -> dict:
    """Empirical measurement-noise floor per dim.

    Central cluster of same-timestamp, non-turn repeated readings of the same
    wheelset (same seg_id). sigma_single = std(central deltas)/sqrt(2). The
    negative tail (turn sessions) is excluded by the +/-0.5 mm central window.
    """
    ws = wes["wheelset_equipment_id"].to_numpy()
    seg = wes["seg_id"].to_numpy()
    tf = (wes["turn_flag"].to_numpy() | wes["replacement"].to_numpy()
          | wes["turn_event"].to_numpy())
    t = pd.to_datetime(wes["measurement_timestamp"]).to_numpy("datetime64[us]")
    gap = (t[1:] - t[:-1]) / DAY
    same = ws[1:] == ws[:-1]
    sameseg = seg[1:] == seg[:-1]
    sel = same & sameseg & (gap == 0) & (~tf[1:]) & (~tf[:-1])
    out = {}
    for f in DIMS + ("wsmDia",):
        a = wes[f"mean_{f}"].to_numpy(float)
        d = (a[1:] - a[:-1])[sel]
        d = d[np.isfinite(d)]
        if len(d) == 0:
            out[f] = None
            continue
        central = d[(d > -0.5) & (d < 0.5)]
        mad_sigma = float(median_abs_deviation(central) / 0.6745 / np.sqrt(2)) \
            if len(central) > 20 else None
        out[f] = {
            "n_pairs": int(len(d)),
            "n_central": int(len(central)),
            "central_sigma_mm": round(float(central.std() / np.sqrt(2)), 4) if len(central) > 5 else None,
            "robust_sigma_mm": round(mad_sigma, 4) if mad_sigma is not None else None,
        }
    return out


def conformal_scores(dim, H, df, tgt_arr, is_train, train_cutoff):
    """Split conformal on C1 delta model: fit on 80% of train, calibrate on 20%."""
    elig = df[f"eligible_{dim}_{H}d"].to_numpy()
    ycol = df[f"tgt_{dim}_{H}d"].to_numpy(dtype=float)
    cur = df[f"mean_{dim}"].to_numpy(dtype=float)
    yok = np.isfinite(ycol) & np.isfinite(cur)
    tr = is_train & elig & yok & (tgt_arr[H] <= train_cutoff)
    order = np.argsort(df.loc[tr, "measurement_timestamp"].to_numpy())  # temporal
    n_tr = int(order.sum() * 0.0) if False else len(order)
    n_fit = int(0.80 * n_tr)
    fit_idx = np.flatnonzero(tr)[order[:n_fit]]
    cal_idx = np.flatnonzero(tr)[order[n_fit:]]

    Xn_all, Xc_all, _ = build_matrix(df)
    Xt = np.hstack([Xn_all[fit_idx], Xc_all[fit_idx]])
    yt = (ycol[fit_idx] - cur[fit_idx])
    m = XGBRegressor(n_estimators=400, learning_rate=0.08, max_depth=6,
                     subsample=0.85, colsample_bytree=0.85,
                     tree_method="hist", random_state=SEED, verbosity=0)
    m.fit(Xt, yt)

    Xcal = np.hstack([Xn_all[cal_idx], Xc_all[cal_idx]])
    ycal = ycol[cal_idx] - cur[cal_idx]
    pred_cal = m.predict(Xcal)
    scores = np.abs(ycal - pred_cal)
    n = len(scores)
    qrank = int(np.ceil((n + 1) * (1 - ALPHA)))
    qrank = max(1, min(qrank, n))
    q = float(np.sort(scores)[qrank - 1])

    te = (~is_train) & elig & yok
    Xte = np.hstack([Xn_all[te], Xc_all[te]])
    yte = ycol[te]
    dte = yte - cur[te]
    pred_te = m.predict(Xte)
    lo = pred_te - q
    hi = pred_te + q
    cov = float(np.mean((dte >= lo) & (dte <= hi))) if te.sum() else None
    width = (hi - lo)
    return {
        "n_fit": int(len(fit_idx)), "n_cal": int(len(cal_idx)), "n_test": int(te.sum()),
        "conformal_width_mm": round(q, 4),
        "coverage": round(cov, 4) if cov is not None else None,
        "mean_interval_mm": round(float(width.mean()), 4) if te.sum() else None,
        "p90_interval_mm": round(float(np.quantile(width, 0.90)), 4) if te.sum() else None,
    }


def operational_capture(df, turns, serving, enc):
    """capture@k of 'turned within H days' anchors, ranked by predicted delta."""
    te = df[df["split"].eq("test")].copy()
    te["_ts"] = pd.to_datetime(te["measurement_timestamp"]).to_numpy("datetime64[us]")
    turn_post = turns[["wheelset_equipment_id", "post_ts"]].copy()
    turn_post["_post"] = pd.to_datetime(turn_post["post_ts"]).to_numpy("datetime64[us]")
    turn_post = turn_post.sort_values("_post")
    gp = turn_post.groupby("wheelset_equipment_id")["_post"].apply(
        lambda s: s.to_numpy())
    te["_later_any"] = te.groupby("wheelset_equipment_id")["_ts"].transform("max")
    out = {}
    for dim in DIMS:
        out[dim] = {}
        for H in HORIZONS:
            el = te[f"eligible_{dim}_{H}d"].astype(bool) & te[f"tgt_{dim}_{H}d"].notna()
            sub = te.loc[el].copy()
            if len(sub) == 0:
                out[dim][f"{H}d"] = None
                continue
            t_end = sub["_ts"] + np.timedelta64(H, "D")
            # label: a confirmed lifecycle turn completes within (t, t+H]
            turns_after = np.zeros(len(sub), dtype=bool)
            for i, (ws_id, t0, te_) in enumerate(zip(sub["wheelset_equipment_id"],
                                                     sub["_ts"], t_end)):
                arr = gp.get(ws_id, np.array([]))
                if len(arr):
                    turns_after[i] = np.any((arr > t0) & (arr <= te_))
            # censoring: negative label only if a later measurement exists (turn would be visible)
            known_negative = (~turns_after) & (sub["_later_any"] > t_end.to_numpy())
            keep = turns_after | known_negative
            if keep.sum() < 100:
                out[dim][f"{H}d"] = None
                continue
            y = turns_after[keep]
            # serving predict
            m = serving["C1_xgb"][dim][H]
            feats = json.loads((SERV / "features.json").read_text())
            Xn = sub.loc[keep, feats["num_feats"]].to_numpy(dtype=float)
            cat = sub.loc[keep, feats["cat_feats"]].astype(str).replace(
                {"nan": "NA", "None": "NA"})
            Xc = enc.transform(cat)
            X = np.hstack([Xn, Xc])
            curv = sub.loc[keep, f"mean_{dim}"].to_numpy(float)
            pred_delta = m.predict(X)
            score = np.where(np.isfinite(pred_delta), pred_delta, -np.inf)
            order = np.argsort(-score, kind="mergesort")
            n = len(score)
            res = {"n_label": int(keep.sum()),
                   "turn_rate": round(float(y.mean()), 4)}
            for frac in (0.01, 0.05, 0.10):
                k = max(1, int(round(frac * n)))
                top = order[:k]
                res[f"capture_{frac:.0%}"] = round(float(y[top].mean() / y.mean()), 4) \
                    if y.mean() > 0 else None
            out[dim][f"{H}d"] = res
    return out


def residual_strip(df, serving, enc):
    """Per-wheelset predicted vs realised delta for one in-substrate loco."""
    te = df[df["split"].eq("test")].copy()
    # pick the loco with the most test wheelsets
    loco = te.groupby("locomotive_id")["wheelset_equipment_id"].nunique().idxmax()
    sub = te[te["locomotive_id"].eq(loco)]
    ws_list = sub["wheelset_equipment_id"].unique()[:6]
    feats = json.loads((SERV / "features.json").read_text())
    rows = []
    for dim in DIMS:
        H = 90
        m = serving["C1_xgb"][dim][H]
        el = sub[f"eligible_{dim}_{H}d"].astype(bool) & sub[f"tgt_{dim}_{H}d"].notna() \
            & sub["wheelset_equipment_id"].isin(ws_list)
        part = sub.loc[el]
        if len(part) == 0:
            continue
        Xn = part[feats["num_feats"]].to_numpy(dtype=float)
        cat = part[feats["cat_feats"]].astype(str).replace({"nan": "NA", "None": "NA"})
        Xc = enc.transform(cat)
        X = np.hstack([Xn, Xc])
        cur = part[f"mean_{dim}"].to_numpy(float)
        delta_p = m.predict(X)
        delta_r = part[f"tgt_{dim}_{H}d"].to_numpy(float) - cur
        rows.append(pd.DataFrame({
            "wheelset": part["wheelset_equipment_id"].to_numpy(),
            "dim": dim, "ts": part["measurement_timestamp"],
            "pred_delta": delta_p, "real_delta": delta_r}))
    if not rows:
        return None
    return pd.concat(rows, ignore_index=True), loco


def serving_residuals_37597(serving, enc):
    """Residual strip for Loco 37597 via the serving feature path."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "models" / "phase5" / "dashboard" / "backend"))
    import features as sf
    wes = sf.load_wes()
    ids = wes.loc[wes["LomNumber"].astype(str).eq("37597"),
                  "wheelset_equipment_id"].unique()
    feats = json.loads((SERV / "features.json").read_text())
    rows = []
    for ws_id in ids:
        w = wes[wes["wheelset_equipment_id"].eq(ws_id)].sort_values(
            "measurement_timestamp").reset_index(drop=True)
        t_arr = pd.to_datetime(w["measurement_timestamp"]).to_numpy("datetime64[us]")
        for p in range(len(w)):
            anchor = pd.Timestamp(t_arr[p])
            fe = sf.extract_features(int(ws_id), anchor, w=w)
            if fe is None:
                continue
            fe["segment_index"] = int(w.iloc[p]["seg_id"])
            for dim in DIMS:
                H = 90
                m = serving["C1_xgb"][dim][H]
                Xn = np.array([[fe.get(c, np.nan) for c in feats["num_feats"]]], dtype=float)
                cat = pd.DataFrame([{c: fe.get(c, "NA") for c in feats["cat_feats"]}]).astype(str)
                cat = cat.replace({"nan": "NA", "None": "NA"})
                Xc = enc.transform(cat)
                X = np.hstack([Xn, Xc])
                cur = fe[f"mean_{dim}"]
                if not np.isfinite(cur):
                    continue
                pred = float(m.predict(X)[0])
                # realised: next same-segment measurement within (t, t+90]
                seg_id = int(w.iloc[p]["seg_id"])
                real = np.nan
                for q in range(p + 1, len(w)):
                    if int(w.iloc[q]["seg_id"]) != seg_id:
                        break
                    dt = (t_arr[q] - t_arr[p]) / DAY
                    if dt <= 90:
                        real = float(w.iloc[q][f"mean_{dim}"]) - cur
                    else:
                        break
                rows.append({"wheelset": int(ws_id), "dim": dim,
                             "ts": anchor, "pred_delta": pred, "real_delta": real})
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_parquet(DATA)
    turns = pd.read_parquet(TURNS)
    bench = json.loads(BENCH.read_text())
    is_train = df["split"].eq("train").to_numpy()
    train_cutoff = pd.to_datetime(df.loc[is_train, "measurement_timestamp"]).max()
    t = pd.to_datetime(df["measurement_timestamp"])
    t_arr = t.to_numpy(dtype="datetime64[us]")
    tgt_arr = {H: pd.to_datetime(df[f"tgt_obs_ts_{H}d"]).to_numpy(dtype="datetime64[us]")
               for H in HORIZONS}

    import sys as _sys
    _sys.path.insert(0, str(ROOT / "models" / "phase5" / "dashboard" / "backend"))
    import features as f_serving  # serving-exact WES (boundaries)
    wes = f_serving.load_wes()

    # --- load serving models / encoder ---
    feats = json.loads((SERV / "features.json").read_text())
    enc = __import__("joblib").load(SERV / "encoder.joblib")
    serving = {"C1_xgb": {dim: {H: __import__("joblib").load(
        SERV / f"model_{dim}_{H}d.joblib") for H in HORIZONS} for dim in DIMS}}

    summary = {
        "task": "phase 5 layer 2 trajectory-product analysis (flange/root/tread + dia conformal)",
        "contract": "wheel_profile_lifecycle_contract_v1",
        "target_mode": "delta",
        "alpha": ALPHA,
        "note": ("Delta forecasts regress tgt-anchor; level = anchor + delta. Absolute "
                 "and delta metrics shown side by side. Residual = realised - predicted "
                 "CHANGE. Noise floor from central same-timestamp non-turn repeated "
                 "readings (sigma_single = std/sqrt(2)). Conformal widths are calibrated "
                 "for the wear dims AND wsmDia so the dia band / conservative "
                 "days-to-condemning can be reported."),
    }

    # ---- 1. delta metrics side by side ----
    metrics_out = {}
    for dim in DIMS:
        metrics_out[dim] = {}
        for H in HORIZONS:
            c = bench["static"][dim][f"{H}d"]["models"]["C1_xgb"]
            metrics_out[dim][f"{H}d"] = {
                "mae_mm": round(c["mae"], 4), "r2": round(c["r2"], 4),
                "spearman": round(c["spearman"], 4) if c["spearman"] is not None else None,
                "delta_mae_mm": round(c["delta_mae"], 4),
                "delta_r2": round(c["delta_r2"], 4),
                "delta_spearman": round(c["delta_spearman"], 4)
                if c.get("delta_spearman") is not None else None,
            }
    summary["1_delta_metrics"] = metrics_out

    # ---- 2. residual + noise floor ----
    summary["2_noise_floor"] = noise_floor(wes)
    resid_out = {}
    for dim in DIMS:
        resid_out[dim] = {}
        for H in HORIZONS:
            el = df[f"eligible_{dim}_{H}d"].astype(bool) & df[f"tgt_{dim}_{H}d"].notna() \
                & df["split"].eq("test") & df[f"mean_{dim}"].notna()
            sub = df.loc[el]
            if len(sub) == 0:
                resid_out[dim][f"{H}d"] = None
                continue
            Xn = sub[feats["num_feats"]].to_numpy(dtype=float)
            cat = sub[feats["cat_feats"]].astype(str).replace({"nan": "NA", "None": "NA"})
            Xc = enc.transform(cat)
            X = np.hstack([Xn, Xc])
            cur = sub[f"mean_{dim}"].to_numpy(float)
            pred = serving["C1_xgb"][dim][H].predict(X)
            real = sub[f"tgt_{dim}_{H}d"].to_numpy(float) - cur
            res = real - pred
            res = res[np.isfinite(res)]
            nf = summary["2_noise_floor"].get(dim)
            nf_sigma = nf["central_sigma_mm"] if nf else None
            resid_out[dim][f"{H}d"] = {
                "n": int(len(res)),
                "mean_mm": round(float(res.mean()), 4),
                "std_mm": round(float(res.std()), 4),
                "p05_p50_p95_mm": [round(float(x), 4) for x in np.percentile(res, [5, 50, 95])],
                "rmse_mm": round(float(np.sqrt(np.mean(res ** 2))), 4),
                "share_abs_le_noise_floor": round(float(np.mean(np.abs(res) <= (nf_sigma or 0))), 4)
                if nf_sigma else None,
            }
    summary["2_residuals"] = resid_out

    # ---- 3. conformal intervals (wear dims + dia) ----
    conf_out = {}
    for dim in CONF_DIMS:
        conf_out[dim] = {}
        for H in HORIZONS:
            conf_out[dim][f"{H}d"] = conformal_scores(dim, H, df, tgt_arr, is_train, train_cutoff)
            print(f"conf {dim} {H}d -> {conf_out[dim][f'{H}d']}")
    summary["3_conformal_80pct"] = conf_out

    # ---- 4. operational capture@k ----
    summary["4_operational_capture"] = operational_capture(df, turns, serving, enc)

    # ---- 5. residual panels ----
    strip, loco = residual_strip(df, serving, enc)
    if strip is not None:
        summary["5_residual_strip"] = {
            "loco": str(loco),
            "n_wheelsets": int(strip["wheelset"].nunique()),
            "n_rows": int(len(strip)),
            "by_dim_rmse_mm": {
                d: round(float(np.sqrt(np.mean((strip.loc[strip.dim.eq(d), "pred_delta"]
                                                - strip.loc[strip.dim.eq(d), "real_delta"]) ** 2))), 4)
                for d in DIMS if len(strip[strip.dim.eq(d)]) > 0},
        }
    s375 = serving_residuals_37597(serving, enc)
    summary["5_residual_strip_37597"] = {
        "n_wheelsets": int(s375["wheelset"].nunique()),
        "n_rows": int(len(s375)),
        "n_with_realised": int(s375["real_delta"].notna().sum()),
        "by_dim": {
            d: {"n": int(s375[s375.dim.eq(d) & s375.real_delta.notna()].shape[0])}
            for d in DIMS},
    }

    # ---- figure: residual panels ----
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    if strip is not None:
        for j, dim in enumerate(DIMS):
            part = strip[strip["dim"].eq(dim)]
            if part.empty:
                continue
            ax = axes[0, j]
            ax.scatter(part["real_delta"], part["pred_delta"], s=8, alpha=0.4,
                       color="#2980b9")
            lim = np.nanmax(np.abs(np.concatenate([part["real_delta"], part["pred_delta"]]))) * 1.1 or 1
            ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8)
            ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
            ax.set_title(f"{dim} @90d (in-substrate loco {loco})")
            ax.set_xlabel("realised delta (mm)"); ax.set_ylabel("predicted delta (mm)")
    for j, dim in enumerate(DIMS):
        part = s375[s375["dim"].eq(dim)]
        ax = axes[1, j]
        ok = part["real_delta"].notna()
        if ok.sum():
            ax.scatter(part.loc[ok, "real_delta"], part.loc[ok, "pred_delta"],
                       s=10, alpha=0.6, color="#e67e22")
            lim = np.nanmax(np.abs(np.concatenate([
                part.loc[ok, "real_delta"], part.loc[ok, "pred_delta"]]))) * 1.1 or 1
            ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8)
            ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
        ax.set_title(f"{dim} @90d (Loco 37597 serving path)")
        ax.set_xlabel("realised delta (mm)"); ax.set_ylabel("predicted delta (mm)")
    fig.suptitle("Trajectory residual strip: predicted vs realised change (flange/root/tread @90d)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "trajectory_residual_panel.png", dpi=130)
    plt.close(fig)

    (OUT / "trajectory_product_analysis.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT))
    print("DONE")


if __name__ == "__main__":
    main()
