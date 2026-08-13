"""Phase 3C - diagnostic forensics (decision gate for Stage C).

Answers, at current observation resolution:

  Which wheel dimensions contain predictable future-state information beyond
  persistence, and how much of the apparent degradation-learning signal is
  destroyed by lifecycle contamination?

Sections
  0. Clean benchmark (persistence / historical-rate / XGBoost, seeded) on the
     frozen within-lifecycle test cohort, per dimension.
  1. Diameter forensics: error distributions, bias, residual by
     interval_days / base diameter / lifecycle segment age / distance.
  2. Root investigation (ML beats persistence): gain + permutation
     importance, seed stability, ROLLING temporal protocol.
  3. Contamination forensics: boundary-row counts, cohort-identity checks,
     ledger confidence classes, A/B full-vs-clean across seeds.
  4. Clean test-set comparison: persistence / historical-rate / clean XGBoost
     on the same cohort.

No hyperparameter tuning. No feature expansion. Alignment-safe.
"""
from __future__ import annotations

import json
from bisect import bisect_left
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))

from degradation_eval import (  # noqa: E402
    ROW_ID_COL, DIMENSIONS,
    add_targets_and_bases, add_historical_rate_predictions,
    assert_row_alignment, chronological_split,
    fit_xgb, _reg_metrics,
)
from run_clean_degradation_benchmark import _base_num_cols, _prepare  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUBSTRATE = ROOT / "model_datasets" / "v3c" / "clean_benchmark_pairs.parquet"
COHORT = ROOT / "model_datasets" / "v3c" / "clean_benchmark_cohort.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3c"
LEDGER = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0" / "engineering_event_ledger.parquet"

SEEDS = [42, 7, 2024]
ROLLING_NWINS = 4


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _pct(arr, qs=(1, 5, 25, 50, 75, 90, 95, 99)) -> dict:
    a = np.asarray(arr, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {q: None for q in qs}
    out = {q: round(float(np.percentile(a, q)), 4) for q in qs}
    out["mean"] = round(float(a.mean()), 4)
    out["std"] = round(float(a.std()), 4)
    out["n"] = int(a.size)
    return out


def _band(v, edges):
    i = bisect_left(edges, float(v))
    if i <= 0:
        return f"<{edges[0]}"
    lo = "" if edges[i] == 1e9 else str(edges[i])
    return f"{edges[i-1]}-{lo}" if lo else f">{edges[i-1]}"


def fit_xgb_seeded(wear, tr_mask, te_mask, dim, cols, seed):
    from xgboost import XGBRegressor
    Xtr = _prepare(wear, cols).loc[tr_mask].to_numpy()
    Xte = _prepare(wear, cols).loc[te_mask].to_numpy()
    y = wear[f"target_{dim}"].to_numpy(dtype=float)
    ytr = np.nan_to_num(y[tr_mask])
    yte = y[te_mask]
    assert_row_alignment(wear.loc[te_mask, ROW_ID_COL].to_numpy(),
                         wear.loc[te_mask, ROW_ID_COL].to_numpy())
    fin = np.isfinite(ytr)
    if fin.sum() < 10:
        m = {"mae": np.nan, "rmse": np.nan, "r2": np.nan, "spearman": np.nan, "n": 0}
        return np.full(Xte.shape[0], np.nan), m
    xgb = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                       subsample=1.0, colsample_bytree=1.0, random_state=seed,
                       n_jobs=-1, tree_method="hist")
    xgb.fit(Xtr[fin], ytr[fin])
    pred = xgb.predict(Xte)
    return pred, _reg_metrics(yte, pred)


def fit_xgb_array(Xtr, Xte, ytr, yte, seed):
    from xgboost import XGBRegressor
    fin = np.isfinite(ytr)
    xgb = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                       subsample=1.0, colsample_bytree=1.0, random_state=seed,
                       n_jobs=-1, tree_method="hist")
    xgb.fit(Xtr[fin], np.nan_to_num(ytr[fin]))
    pred = xgb.predict(Xte)
    return pred, _reg_metrics(yte, pred)


def _bias_map(resid: pd.DataFrame, name: str) -> dict:
    """Group residual frame by `name`, report bias + MAE per group."""
    def row(g):
        return {"n": int(len(g)),
                "persistence_bias": round(float(g["persist_resid"].mean()), 4),
                "xgb_bias": round(float(g["xgb_resid"].mean()), 4),
                "persistence_mae": round(float(g["persist_err_abs"].mean()), 4),
                "xgb_mae": round(float(g["xgb_err_abs"].mean()), 4)}
    return {str(k): row(v) for k, v in resid.groupby(name, dropna=False)}


def _banded(resid: pd.DataFrame, col: str, edges) -> dict:
    """Band `col` by `edges` and report bias + MAE per band."""
    ser = pd.Series([_band(v, edges) for v in resid[col]], index=resid.index)
    g = resid.assign(_b=ser.to_numpy()).groupby("_b")
    return {str(k): {"n": int(len(v)),
                     "persistence_bias": round(float(v["persist_resid"].mean()), 4),
                     "xgb_bias": round(float(v["xgb_resid"].mean()), 4),
                     "persistence_mae": round(float(v["persist_err_abs"].mean()), 4),
                     "xgb_mae": round(float(v["xgb_err_abs"].mean()), 4)}
            for k, v in g}


def _lifecycle_age_days(wear: pd.DataFrame) -> pd.Series:
    """Days since the first measurement of the current lifecycle segment."""
    w = wear.copy()
    w["_t"] = pd.to_datetime(w["measurement_timestamp"])
    first = w.groupby(["wheelset_equipment_id", "lifecycle_segment_id"], sort=False)["_t"].transform("min")
    age = (w["_t"] - first).dt.total_seconds() / 86400.0
    return age.reindex(wear.index)


def rolling_indices(wear: pd.DataFrame, n: int = 4):
    """Expanding-window ROLLING protocol over the within-life sorted frame.
    Window i trains on rows with rank <= te-start of window i (expanding) and
    evaluates on the ith temporal test window. Returns (tr_ids, te_ids)."""
    w = wear.sort_values("measurement_timestamp").reset_index(drop=True)
    ids = w[ROW_ID_COL].to_numpy()
    n_rows = len(ids)
    edges_full = np.linspace(0, n_rows, n + 1).astype(int)
    out = []
    for i in range(n):
        te_slice = np.arange(edges_full[i], edges_full[i + 1])
        tr_slice = np.arange(0, te_slice[0])  # expanding: everything before
        out.append((ids[tr_slice], ids[te_slice]))
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    wear_all_raw = pd.read_parquet(SUBSTRATE)
    wear = wear_all_raw[wear_all_raw["within_lifecycle"]].copy()
    wear = add_targets_and_bases(wear)
    wear = add_historical_rate_predictions(wear)
    wear_sorted, tr_mask, te_mask = chronological_split(wear, test_frac=0.2, cache_path=COHORT)
    te = wear_sorted.loc[te_mask]
    test_ids = te[ROW_ID_COL].to_numpy()
    cols = _base_num_cols()

    out: dict = {
        "task": "Phase 3C diagnostic forensics (decision gate, no tuning)",
        "seeds": SEEDS,
        "n_train": int(tr_mask.sum()),
        "n_test": int(te_mask.sum()),
        "split": "chronological 80/20 frozen cohort",
        "frozen_cohort": str(COHORT.relative_to(ROOT)),
    }

    # ------------------------------------------------------------------ #
    # 0. benchmark per dimension x seed
    # ------------------------------------------------------------------ #
    bench = {}
    pred_dia = {}
    for d in DIMENSIONS:
        yt = te[f"target_{d}"].to_numpy(dtype=float)
        yb = te[f"base_{d}"].to_numpy(dtype=float)
        m_pers = _reg_metrics(yt, yb)
        m_hist = _reg_metrics(yt, te[f"pred_{d}"].to_numpy(dtype=float))
        seed_m = {}
        pred_s = None
        for sd in SEEDS:
            pred_s, m = fit_xgb_seeded(wear_sorted, tr_mask, te_mask, d, cols, seed=sd)
            seed_m[str(sd)] = m
            if d == "wsmDia" and sd == 42:
                pred_dia = pred_s
        xgb_mae = np.array([seed_m[s]["mae"] for s in seed_m])
        bench[d] = {
            "persistence": m_pers,
            "historical_rate": m_hist,
            "xgb_per_seed": seed_m,
            "xgb_mae_mean": float(xgb_mae.mean()),
            "xgb_mae_sd": float(xgb_mae.std()),
            "delta_mae_vs_persistence_mean": round(float(xgb_mae.mean()) - m_pers["mae"], 4),
        }
    out["benchmark"] = bench

    # ------------------------------------------------------------------ #
    # 1. diameter forensics (seed 42)
    # ------------------------------------------------------------------ #
    yt = te["target_wsmDia"].to_numpy(dtype=float)
    yb = te["base_wsmDia"].to_numpy(dtype=float)
    age = _lifecycle_age_days(te)

    resid = pd.DataFrame({
        "target": yt, "persist_pred": yb, "xgb_pred": pred_dia,
        "persist_resid": yt - yb, "xgb_resid": yt - pred_dia,
        "persist_err_abs": np.abs(yt - yb), "xgb_err_abs": np.abs(yt - pred_dia),
        "interval_days": te["interval_days"].to_numpy(),
        "distance_per_day_km": te["distance_per_day_km"].to_numpy(),
        "distance_available": te["distance_available"].fillna(False).astype(bool).to_numpy(),
        "base_dia": yb,
        "lifecycle_age_days": age.to_numpy(),
    }).dropna(subset=["persist_resid", "xgb_resid"])

    dia = {
        "n": int(np.isfinite(yt).sum()),
        "persistence_err_abs": _pct(np.abs(yt - yb)),
        "xgb_err_abs": _pct(np.abs(yt - pred_dia)),
        "persistence_resid": _pct(yt - yb),
        "xgb_resid": _pct(yt - pred_dia),
        "bias_persistence": round(float((yt - yb).mean()), 4),
        "bias_xgb": round(float((yt - pred_dia).mean()), 4),
        "resid_by_interval_days": _banded(resid, "interval_days", [0, 30, 60, 90, 180, 1e9]),
        "resid_by_distance_per_day_km": _banded(resid, "distance_per_day_km", [0, 250, 450, 650, 1e9]),
        "resid_by_distance_available": _bias_map(resid, "distance_available"),
        "resid_by_lifecycle_age_days": _banded(resid, "lifecycle_age_days", [0, 100, 300, 700, 1500, 1e9]),
    }
    dia_edges = np.quantile(resid["base_dia"].dropna(), [0, 0.2, 0.4, 0.6, 0.8, 1.0])
    resid["dia_bin"] = pd.cut(resid["base_dia"], bins=dia_edges)
    dia["resid_by_base_diameter"] = {
        str(k): {"n": int(len(v)),
                 "persistence_bias": round(float(v["persist_resid"].mean()), 4),
                 "xgb_bias": round(float(v["xgb_resid"].mean()), 4),
                 "persistence_mae": round(float(v["persist_err_abs"].mean()), 4),
                 "xgb_mae": round(float(v["xgb_err_abs"].mean()), 4)}
        for k, v in resid.groupby("dia_bin", dropna=False)}
    out["diameter_forensics"] = dia

    # ------------------------------------------------------------------ #
    # 2. root investigation
    # ------------------------------------------------------------------ #
    root = {}
    # 2.1 model object from seed 42, test predictions
    from xgboost import XGBRegressor
    Xtr_r = _prepare(wear_sorted, cols).loc[tr_mask].to_numpy()
    Xte_r = _prepare(wear_sorted, cols).loc[te_mask].to_numpy()
    ytr_r = np.nan_to_num(wear_sorted["target_wsmRoot"].to_numpy(dtype=float)[tr_mask])
    yte_r = wear_sorted["target_wsmRoot"].to_numpy(dtype=float)[te_mask]
    mdl = XGBRegressor(n_estimators=250, max_depth=6, learning_rate=0.1,
                       subsample=1.0, colsample_bytree=1.0, random_state=42,
                       n_jobs=-1, tree_method="hist")
    mdl.fit(Xtr_r, ytr_r)
    root_pred = mdl.predict(Xte_r)
    base_m = _reg_metrics(yte_r, root_pred)
    root["baseline_test_metrics_seed42"] = base_m
    root["persistence_test_metrics"] = _reg_metrics(yte_r, te["base_wsmRoot"].to_numpy(dtype=float))

    # 2.2 permutation importance (drop in test MAE when feature shuffled)
    rng = np.random.default_rng(42)
    perm = {}
    for j, c in enumerate(cols):
        Xp = Xte_r.copy()
        Xp[:, j] = Xte_r[rng.permutation(Xte_r.shape[0]), j]
        pm = _reg_metrics(yte_r, mdl.predict(Xp))
        perm[c] = round(float(pm["mae"] - base_m["mae"]), 5)
    root["permutation_top_mae_drop"] = sorted(perm.items(), key=lambda kv: -kv[1])[:15]

    # 2.3 gain + weight importance
    booster = mdl.get_booster()
    root["gain_importance"] = dict(
        sorted(booster.get_score(importance_type="gain").items(), key=lambda kv: -kv[1])[:15])
    root["weight_importance"] = dict(
        sorted(booster.get_score(importance_type="weight").items(), key=lambda kv: -kv[1])[:15])

    # 2.4 seed stability (from bench)
    root["xgb_seed_stability"] = {
        "mae_per_seed": bench["wsmRoot"]["xgb_per_seed"],
        "mean": bench["wsmRoot"]["xgb_mae_mean"],
        "sd": bench["wsmRoot"]["xgb_mae_sd"],
        "persistence_mae": bench["wsmRoot"]["persistence"]["mae"],
    }

    # 2.5 rolling temporal protocol (expanding windows)
    rolling = rolling_indices(wear_sorted, n=ROLLING_NWINS)
    roll_out = {}
    for i, (tr_ids, te_ids) in enumerate(rolling):
        trm = wear_sorted[ROW_ID_COL].isin(tr_ids)
        tem = wear_sorted[ROW_ID_COL].isin(te_ids)
        row = {"n": int(tem.sum())}
        for d in DIMENSIONS:
            yt = wear_sorted[f"target_{d}"].to_numpy(dtype=float)[tem.to_numpy()]
            ybb = wear_sorted[f"base_{d}"].to_numpy(dtype=float)[tem.to_numpy()]
            row.setdefault(d, {})
            row[d]["persistence"] = _reg_metrics(yt, ybb)["mae"]
            _, m2 = fit_xgb_seeded(wear_sorted, trm, tem, d, cols, seed=42)
            row[d]["xgb"] = m2["mae"]
        roll_out[f"win{i}"] = row
    root["rolling_temporal"] = roll_out
    out["root_forensics"] = root

    # ------------------------------------------------------------------ #
    # 3. contamination forensics
    # ------------------------------------------------------------------ #
    w_all = add_targets_and_bases(wear_all_raw)
    w_all_sorted = w_all.sort_values("measurement_timestamp").reset_index(drop=True)
    te_set = set(te[ROW_ID_COL].to_numpy())
    tr_all = ~w_all_sorted[ROW_ID_COL].isin(te_set)
    te_all = w_all_sorted[ROW_ID_COL].isin(te_set)

    # cohort identity checks
    test_ids_full = w_all_sorted.loc[te_all, ROW_ID_COL].to_numpy()
    ident_ok = (len(test_ids_full) == len(test_ids) and
                set(test_ids_full) == set(test_ids))

    # Event Ledger confidence classes (CONFIRMED vs LIKELY)
    from build_clean_benchmark_substrate import crosses_replacement_mask
    from degradation_eval import ROW_ID_COL as _R  # noqa
    led = pd.read_parquet(LEDGER)

    def _mask_for_confidences(conf):
        rep = led[(led["event_type"] == "replacement") &
                  (led["confidence"].isin(conf))].dropna(subset=["event_date"])
        m = {}
        for k, g in rep.groupby("wheelset_equipment_id"):
            wid = int(k)
            m[wid] = np.sort(pd.to_datetime(g["event_date"]).to_numpy(dtype="datetime64[us]"))
        return crosses_replacement_mask(w_all_sorted, m)

    mask_conf_only = _mask_for_confidences(["CONFIRMED"])
    mask_conf_likely = _mask_for_confidences(["CONFIRMED", "LIKELY"])
    mask_likely_only = (mask_conf_likely & ~mask_conf_only)

    cont = {
        "rows_total": int(len(w_all)),
        "rows_within_lifecycle": int(w_all.within_lifecycle.sum()),
        "crosses_replacement_all": int(w_all.crosses_replacement.sum()),
        "crosses_replacement_full_train": int(w_all_sorted.loc[tr_all, "crosses_replacement"].sum()),
        "crosses_replacement_test": int(w_all_sorted.loc[te_all, "crosses_replacement"].sum()),
        "crosses_reset_full_train": int(w_all_sorted.loc[tr_all, "crosses_reset"].sum()),
        "crosses_reset_test": int(w_all_sorted.loc[te_all, "crosses_reset"].sum()),
        "test_cohort_identical_full_vs_clean": ident_ok,
        "test_cohort_replacement_or_reset_crossings": int(
            w_all_sorted.loc[te_all, ["crosses_replacement", "crosses_reset"]].to_numpy().sum()),
        "replacement_events_CONFIRMED": int(len(led[(led.event_type.eq("replacement")) & (led.confidence.eq("CONFIRMED"))])),
        "replacement_events_LIKELY": int(len(led[(led.event_type.eq("replacement")) & (led.confidence.eq("LIKELY"))])),
        "rows_cross_replacement_conf_only": int(mask_conf_only.sum()),
        "rows_cross_replacement_conf_or_likely": int(mask_conf_likely.sum()),
        "rows_cross_replacement_likely_only": int(mask_likely_only.sum()),
    }
    out["contamination"] = cont

    # 3b. A/B full-vs-clean training (same frozen test cohort), >=3 seeds
    ab = {}
    for sd in SEEDS:
        row = {}
        XtrA = _prepare(w_all_sorted, cols).loc[tr_all].to_numpy()
        XteA = _prepare(w_all_sorted, cols).loc[te_all].to_numpy()
        for d in DIMENSIONS:
            yA = w_all_sorted[f"target_{d}"].to_numpy(dtype=float)
            yteA = yA[te_all]
            _, m_all = fit_xgb_array(XtrA, XteA, yA[tr_all], yteA, sd)
            m_cln = bench[d]["xgb_per_seed"][str(sd)]
            diff = m_all["mae"] - m_cln["mae"]
            row[d] = {"full_train_mae": m_all["mae"],
                      "clean_train_mae": m_cln["mae"],
                      "delta_mae_full_minus_clean": round(diff, 4),
                      "relative_delta_full_vs_clean": round(float(diff / m_all["mae"]), 4)}
        ab[f"seed_{sd}"] = row
    seed_keys = [f"seed_{sd}" for sd in SEEDS]
    for d in DIMENSIONS:
        fs = [ab[s][d]["full_train_mae"] for s in seed_keys]
        cs = [ab[s][d]["clean_train_mae"] for s in seed_keys]
        ds = [ab[s][d]["delta_mae_full_minus_clean"] for s in seed_keys]
        ab["agg_" + d] = {
            "full_mae_mean": round(float(np.mean(fs)), 4),
            "full_mae_sd": round(float(np.std(fs)), 4),
            "clean_mae_mean": round(float(np.mean(cs)), 4),
            "clean_mae_sd": round(float(np.std(cs)), 4),
            "delta_mean": round(float(np.mean(ds)), 4),
            "delta_sd": round(float(np.std(ds)), 4),
        }
    out["contamination_ab"] = ab

    # ------------------------------------------------------------------ #
    # write output
    # ------------------------------------------------------------------ #
    OUTPUT.mkdir(parents=True, exist_ok=True)
    op = OUTPUT / "diagnostic_forensics_results.json"
    op.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(op)
    print(f"train={int(tr_mask.sum())} test={int(te_mask.sum())}")
    for d in DIMENSIONS:
        b = bench[d]
        print(f"{d:18s} persist={b['persistence']['mae']:.4f} "
              f"hist_rate={b['historical_rate']['mae']:.4f} "
              f"xgb={b['xgb_mae_mean']:.4f}±{b['xgb_mae_sd']:.4f} "
              f"d_vs_persist={b['delta_mae_vs_persistence_mean']:+.4f}")


if __name__ == "__main__":
    main()