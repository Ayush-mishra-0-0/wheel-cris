"""Layer 5 - wear-rate serving head (Option 3: rate + integrate) + champion choice.

Trains ONE XGBoost per dimension on the DENSE adjacent same-segment pair rate
(stage 3, wear_rate_substrate.parquet): Y = mean_wear change per day between an
anchor and its next no-turn within-segment measurement. At serve time the
30/90/180 d values are the integrals pred_h = current + rate * h, which are
monotone by construction (no cross-horizon consistency failures).

PIT discipline (mirrors build_serving_models.py): training labels only count
when the NEXT observation timestamp is at or before the train cutoff, so every
training example would have been knowable at deployment time.

Champion/backup contract:
  - Backups the CURRENT per-horizon head (serving/degradation) untouched.
  - Benchmarks BOTH on the frozen v5 TEST cohort, evaluating the SERVED path
    (per-horizon deltas passed through the monotone no-turn reconciliation that
    the dashboard applies) so the comparison is exactly what the UI renders.
  - Writes champion.json with a per-dimension model-of-record decision
    (lower mean level-MAE across 30/90/180 d wins). service.py reads this to
    choose the source per dimension and falls back to the per-horizon head when
    the rate head is absent/worse.

Outputs (serving/degradation_rate/):
  model_<dim>.joblib        rate-per-day regressor per dimension
  encoder.joblib / features.json / manifest.json
  champion.json             benchmark + served model-of-record decision
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "model_datasets" / "v5" / "wear_rate_substrate.parquet"
CUR = ROOT / "models" / "phase5" / "serving" / "degradation"
OUT = ROOT / "models" / "phase5" / "serving" / "degradation_rate"
EXP = ROOT / "models" / "experiments" / "v5"

HORIZONS = (30, 90, 180)
DIMS = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
SEED = 42


def _load_schema(d: Path) -> tuple[list[str], list[str]]:
    feats = json.loads((d / "features.json").read_text())
    return list(feats["num_feats"]), list(feats["cat_feats"])


NUM_FEATS, CAT_FEATS = _load_schema(CUR)


def build_matrix(df: pd.DataFrame, enc=None, num=None, cat=None):
    Xn = df[num].to_numpy(dtype=float)
    catdf = df[cat].astype(str).replace({"nan": "NA", "None": "NA"})
    if enc is None:
        enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        Xc = enc.fit_transform(catdf)
    else:
        Xc = enc.transform(catdf)
    return np.hstack([Xn, Xc]), enc


def served_path(dim: str, deltas: dict[int, float]) -> dict[int, float]:
    """Monotone no-turn serving path (same contract as service._no_turn_monotone)."""
    down = dim == "wsmDia"
    out: dict[int, float] = {}
    prev = 0.0
    for h in sorted(deltas):
        d = float(deltas[h])
        if not np.isfinite(d):
            out[h] = np.nan
            continue
        prev = min(prev, d) if down else max(prev, d)
        prev = min(prev, 0.0) if down else max(prev, 0.0)
        out[h] = prev
    return out


def level_metrics(yt, cur, delta_h):
    yt = np.asarray(yt, float)
    cur = np.asarray(cur, float)
    dh = np.asarray(delta_h, float)
    ok = np.isfinite(yt) & np.isfinite(cur) & np.isfinite(dh)
    y, yh = yt[ok], cur[ok] + dh[ok]
    if len(y) < 10:
        return None
    mae = float(np.mean(np.abs(y - yh)))
    rmse = float(np.sqrt(np.mean((y - yh) ** 2)))
    ss = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = float(1.0 - np.sum((y - yh) ** 2) / ss)
    try:
        ris = spearmanr(y, yh)
        rho = float(getattr(ris, "statistic", ris[0]))
    except Exception:
        rho = None
    return {"mae": mae, "rmse": rmse, "r2": r2, "spearman": rho,
            "n": int(len(y)), "delta_mae": float(np.mean(np.abs((yt - cur)[ok] - dh[ok])))}


def fit_decay_k(d_act, d_rate):
    """Constrained-OOS-decay scale k = argmin_k sum((d_act - k*d_rate)^2), k>0.

    Fits the horizon deceleration factor so the integrated path is
    delta_H = k * rate * H (delta(0)=0 by construction, monotone in H).
    """
    d_act = np.asarray(d_act, float)
    d_rate = np.asarray(d_rate, float)
    ok = np.isfinite(d_act) & np.isfinite(d_rate) & (d_rate != 0)
    if ok.sum() < 30:
        return 1.0
    num = float(np.sum(d_act[ok] * d_rate[ok]))
    den = float(np.sum(d_rate[ok] ** 2))
    if den <= 0 or num <= 0:
        return 1.0
    return min(5.0, max(0.0, num / den))


def main() -> None:
    df = pd.read_parquet(DATA)
    tgt_arr = pd.to_datetime(df["next_obs_ts"]).to_numpy(dtype="datetime64[us]")
    is_train = df["split"].eq("train").to_numpy()
    is_test = df["split"].eq("test").to_numpy()
    train_cutoff = pd.to_datetime(df.loc[is_train, "measurement_timestamp"]).max()

    Xn_all = df[NUM_FEATS].to_numpy(dtype=float)
    cat = df[CAT_FEATS].astype(str).replace({"nan": "NA", "None": "NA"})
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    Xc_all = enc.fit_transform(cat)

    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump(enc, OUT / "encoder.joblib")
    features_doc = {
        "num_feats": NUM_FEATS, "cat_feats": CAT_FEATS,
        "target_dims": list(DIMS), "target": "wear_rate_per_day",
        "integrate": "pred_h = current + rate * h (mm)",
        "horizons": list(HORIZONS),
        "train_cutoff": str(train_cutoff.date()),
        "n_train_rows": int(is_train.sum()),
    }
    (OUT / "features.json").write_text(
        json.dumps(features_doc, indent=2) + "\n", encoding="utf-8")

    # ---------------- train one rate head per dimension ----------------
    rate_models: dict[str, object] = {}
    manifest = {"task": "phase 5 layer 2 wear-rate serving head (Option 3)",
                "target": "per-day mm rate, integrated by horizon",
                "note": "Backup to the per-horizon delta head kept in serving/degradation.",
                "models": []}
    for dim in DIMS:
        y = df[f"rate_{dim}"].to_numpy(dtype=float)
        yok = np.isfinite(y)
        tr = is_train & yok & (tgt_arr <= train_cutoff)
        Xtr = np.hstack([Xn_all[tr], Xc_all[tr]])
        ytr = y[tr]
        m = XGBRegressor(n_estimators=400, learning_rate=0.08, max_depth=6,
                         subsample=0.85, colsample_bytree=0.85,
                         tree_method="hist", random_state=SEED, verbosity=0)
        m.fit(Xtr, ytr)
        joblib.dump(m, OUT / f"model_{dim}.joblib")
        rate_models[dim] = m
        manifest["models"].append({
            "dim": dim, "path": f"model_{dim}.joblib",
            "n_train": int(len(ytr)),
            "substrate": "wear_rate_substrate.parquet",
        })
        print(f"{dim} rate head  train={len(ytr):,}")
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # ---------------- benchmark on the frozen TEST cohort ----------------
    cur_svc = {dim: {h: joblib.load(CUR / f"model_{dim}_{h}d.joblib")
                     for h in HORIZONS} for dim in DIMS}

    tgt_obs_arr = {h: pd.to_datetime(df[f"tgt_obs_ts_{h}d"]).to_numpy(dtype="datetime64[us]")
                   for h in HORIZONS}
    cur_pred = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    rate_raw = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    rate_cal = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    decay_k = {}
    Xtest_full = np.hstack([Xn_all, Xc_all])
    y_cur = {dim: {h: df[f"mean_{dim}"].to_numpy(dtype=float) for h in HORIZONS}
             for dim in DIMS}
    for dim in DIMS:
        rate = rate_models[dim].predict(Xtest_full)
        for h in HORIZONS:
            rate_raw[dim][h] = rate * h
            cur_pred[dim][h] = cur_svc[dim][h].predict(Xtest_full)
            # decay scale fit on TRAIN-only horizon pairs (label knowable at cutoff)
            cur_ = df[f"mean_{dim}"].to_numpy(dtype=float)
            el_tr = is_train & df[f"eligible_{dim}_{h}d"].to_numpy() & \
                df[f"tgt_{dim}_{h}d"].notna() & (tgt_obs_arr[h] <= train_cutoff)
            d_act = df.loc[el_tr, f"tgt_{dim}_{h}d"].to_numpy(dtype=float) - cur_[el_tr]
            d_rate = rate[el_tr] * h
            k = fit_decay_k(d_act, d_rate)
            decay_k[(dim, h)] = round(float(k), 4)
            rate_cal[dim][h] = k * rate * h

    # served (= dashboard-rendered) paths: monotone no-turn applied to both heads
    served_cur = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    served_rate = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    served_cal = {dim: {h: np.full(len(df), np.nan) for h in HORIZONS} for dim in DIMS}
    for i in range(len(df)):
        for dim in DIMS:
            pc = served_path(dim, {h: float(cur_pred[dim][h][i]) for h in HORIZONS})
            pr = served_path(dim, {h: float(rate_raw[dim][h][i]) for h in HORIZONS})
            pk = served_path(dim, {h: float(rate_cal[dim][h][i]) for h in HORIZONS})
            for h in HORIZONS:
                served_cur[dim][h][i] = pc[h]
                served_rate[dim][h][i] = pr[h]
                served_cal[dim][h][i] = pk[h]

    cells: dict = {}
    for dim in DIMS:
        cells[dim] = {}
        for h in HORIZONS:
            el = df[f"eligible_{dim}_{h}d"].to_numpy() & df[f"tgt_{dim}_{h}d"].notna()
            cohort = is_test & el & np.isfinite(df[f"rate_{dim}"].to_numpy(dtype=float))
            yt = df[f"tgt_{dim}_{h}d"].to_numpy(dtype=float)
            cur = df[f"mean_{dim}"].to_numpy(dtype=float)
            cells[dim][f"{h}d"] = {
                "n": int(cohort.sum()),
                "decay_k": decay_k.get((dim, h)),
                "current_src_raw": level_metrics(yt[cohort], cur[cohort], cur_pred[dim][h][cohort]),
                "current_src_served": level_metrics(yt[cohort], cur[cohort], served_cur[dim][h][cohort]),
                "rate_raw": level_metrics(yt[cohort], cur[cohort], rate_raw[dim][h][cohort]),
                "rate_served": level_metrics(yt[cohort], cur[cohort], served_rate[dim][h][cohort]),
                "rate_calibrated_raw": level_metrics(yt[cohort], cur[cohort], rate_cal[dim][h][cohort]),
                "rate_calibrated_served": level_metrics(yt[cohort], cur[cohort], served_cal[dim][h][cohort]),
            }

    # consistency diagnostic (the product failure) on the full test set
    te_pos = np.flatnonzero(is_test)
    cons = {"current_src_raw": {}, "rate_raw": {}}
    for dim in DIMS:
        down = dim == "wsmDia"
        for tag, arr in (("current_src_raw", cur_pred), ("rate_raw", rate_raw)):
            n_ok = 0
            viol = 0
            for i in te_pos:
                d30, d90, d180 = (arr[dim][30][i], arr[dim][90][i], arr[dim][180][i])
                if not (np.isfinite(d30) and np.isfinite(d90) and np.isfinite(d180)):
                    continue
                n_ok += 1
                bad = (d90 > d180) or (d30 > d90) if not down else (d90 < d180) or (d30 < d90)
                if bad:
                    viol += 1
            cons[tag][dim] = {"n": n_ok,
                              "non_monotone_rate_pct": round((viol / n_ok) * 100, 3) if n_ok else None}

    # ---------------- champion decision (per dimension) ----------------
    dim_choice: dict[str, str] = {}
    agg_cur = agg_cal = 0.0
    for dim in DIMS:
        maes_cur = [cells[dim][f"{h}d"]["current_src_served"]["mae"]
                    for h in HORIZONS
                    if cells[dim][f"{h}d"]["current_src_served"]]
        maes_cal = [cells[dim][f"{h}d"]["rate_calibrated_served"]["mae"]
                    for h in HORIZONS
                    if cells[dim][f"{h}d"]["rate_calibrated_served"]]
        if maes_cur and maes_cal:
            dim_choice[dim] = "wear_rate" if np.mean(maes_cal) <= np.mean(maes_cur) else "per_horizon_xgb"
            agg_cur += float(np.mean(maes_cur))
            agg_cal += float(np.mean(maes_cal))
        else:
            dim_choice[dim] = "per_horizon_xgb"
    agg_choice = "wear_rate" if agg_cal <= agg_cur else "per_horizon_xgb"

    champion = {
        "basis": ("Served no-turn path on frozen v5 TEST cohort; per-dim decision = "
                  "lower mean level-MAE across 30/90/180 d on the shared cohort "
                  "(anchor has both a rate pair and the horizon target). The wear-rate "
                  "head integrates delta_H = decay_k(dim,H) * rate * H; decay_k is fit "
                  "on TRAIN-only horizon pairs (wear decelerates, so naive rate*H "
                  "over-predicts long horizons)."),
        "train_cutoff": str(train_cutoff.date()),
        "agg_served_mae_current_mm": round(agg_cur, 4),
        "agg_served_mae_rate_calibrated_mm": round(agg_cal, 4),
        "aggregate_model_of_record": agg_choice,
        "dim_model_of_record": dim_choice,
        "decay_k": {f"{dim}_{h}d": decay_k[(dim, h)] for dim in DIMS for h in HORIZONS},
        "per_dim_horizon": cells,
        "consistency_test": cons,
        "n_test": int(is_test.sum()),
        "sha256": hashlib.sha256(json.dumps(cells, sort_keys=True).encode()).hexdigest()[:10],
    }
    (OUT / "champion.json").write_text(
        json.dumps(champion, indent=2, default=str) + "\n", encoding="utf-8")
    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / "wear_rate_champion.json").write_text(
        json.dumps(champion, indent=2, default=str) + "\n", encoding="utf-8")

    print(json.dumps({"aggregate_model_of_record": agg_choice,
                      "dim_model_of_record": dim_choice,
                      "agg_served_mae_current_mm": round(agg_cur, 4),
                      "agg_served_mae_rate_calibrated_mm": round(agg_cal, 4),
                      "decay_k": {f"{dim}_{h}d": decay_k[(dim, h)] for dim in DIMS for h in HORIZONS}},
                     indent=2))
    for dim in DIMS:
        for h in HORIZONS:
            c = cells[dim][f"{h}d"]
            cur_s = c["current_src_served"]
            r_c = c["rate_calibrated_served"]
            print(f"{dim:10s} {h}d  n={c['n']:>6,}  k={c['decay_k']}  current_served_mae={cur_s['mae'] if cur_s else None:>7.4f}"
                  f" | rate_cal_served_mae={r_c['mae'] if r_c else None:>7.4f}")
    for tag in ("current_src_raw", "rate_raw"):
        print(tag, {d: cons[tag][d]["non_monotone_rate_pct"] for d in DIMS})
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=FutureWarning)
    main()