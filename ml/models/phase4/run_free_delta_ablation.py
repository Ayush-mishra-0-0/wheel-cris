"""Phase 4 - free-delta ablation on Target B ranking (+ calibration comparison).

Question (action plan priority 3): do the already-validated free deltas
(flange-thickness/root/gauge/tire-thickness step deltas, gap length, skid flag)
add ranking lift over the shipping B1 state/context set?

Protocol is IDENTICAL to the committed benchmarks so numbers are comparable:
  * anchors/labels/split: frozen model_datasets/v4/risk_benchmark.parquet
    (built on WES v1.0; rebuilt benchmarks on v1.1 are a separate post-signoff
    step - comparability with committed numbers is preserved here).
  * models: B0 prevalence, B1 LogisticRegression(C=0.1, max_iter=1000,
    random_state=SEED) on StandardScaler - exactly run_rolling_risk_benchmark.
  * metrics: PR-AUC, ROC-AUC, Brier, ECE, capture@5/10%, lift@5/10%.
  * evaluations:
      A. frozen train/test split (final_benchmark_report protocol)
      B. never-seen-loco holdout (~20% locos, seed 42; transfer stress)
  * leakage: free deltas are BACKWARD-looking (value - previous value) joined
    by measurement_record_id; has_prior_measurement=0 rows carry NaN deltas,
    which nan_to_num handles identically in both arms.

Calibration comparison (Target B, winning arm): production decile-band
(train-decile empirical rate, as served today) vs isotonic regression fit on
the same train scores. Compared on test ECE / Brier + 10-bin reliability.

Output: models/experiments/v4/free_delta_ablation.json (+ printed table).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_rolling_risk_benchmark import (  # noqa: E402
    HORIZONS, SEED, build_matrix, capture_at, ece, lift_at, pr_auc, roc_auc,
)
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "model_datasets" / "v4" / "risk_benchmark.parquet"
DELTAS = ROOT / "model_datasets" / "v5" / "free_delta_features_v1.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v4"

# Backward-looking delta block (point-in-time safe; means are already in B1).
DELTA_FEATS = [
    "flange_thickness_delta_mm", "root_delta_mm", "wheel_gauge_delta_mm",
    "tire_thickness_delta_mm", "days_since_previous_measurement",
    "has_prior_measurement", "skid_flag",
]


def brier(p, y):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    return float(np.mean((p - y) ** 2))


def decile_band_fit(ptr, ytr):
    """Production-style calibration: train-score deciles -> empirical rate."""
    ptr = np.asarray(ptr, float)
    edges = np.unique(np.quantile(ptr, np.linspace(0, 1, 11)[1:-1]))
    idx = np.clip(np.digitize(ptr, edges), 0, len(edges))
    rates = np.array([float(np.mean(ytr[idx == k])) if (idx == k).any() else np.nan
                      for k in range(len(edges) + 1)])
    # fill empty bins by nearest valid rate
    valid = np.flatnonzero(np.isfinite(rates))
    for k in range(len(rates)):
        if not np.isfinite(rates[k]) and valid.size:
            rates[k] = rates[valid[np.argmin(np.abs(valid - k))]]
    return {"edges": edges.tolist(), "rates": rates.tolist()}


def decile_band_apply(band, p):
    edges = np.asarray(band["edges"]); rates = np.asarray(band["rates"])
    idx = np.clip(np.digitize(np.asarray(p, float), edges), 0, len(rates) - 1)
    return rates[idx]


def reliability(p, y, bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for k in range(bins):
        m = idx == k
        if m.sum() < 5:
            continue
        out.append({"bin": k, "n": int(m.sum()),
                    "mean_pred": round(float(p[m].mean()), 5),
                    "empirical": round(float(y[m].mean()), 5)})
    return out


def fit_b1(Xtr, ytr, Xsc):
    Xtrf = np.nan_to_num(Xtr, nan=0.0); Xscf = np.nan_to_num(Xsc, nan=0.0)
    s = StandardScaler().fit(Xtrf)
    lr = LogisticRegression(C=0.1, max_iter=1000, random_state=SEED)
    lr.fit(s.transform(Xtrf), ytr)
    return lr.predict_proba(s.transform(Xscf))[:, 1]


def cell(p, y):
    prev = float(np.nanmean(y)) if len(y) else None
    return {
        "n": int(len(y)), "events": int(np.nansum(y)), "prevalence": round(prev, 5) if prev is not None else None,
        "pr_auc": pr_auc(p, y), "roc_auc": roc_auc(p, y),
        "brier": brier(p, y), "ece": ece(p, y),
        "capture5": capture_at(p, y, 0.05), "capture10": capture_at(p, y, 0.10),
        "lift5": lift_at(p, y, 0.05), "lift10": lift_at(p, y, 0.10),
    }


def r(x):
    return None if x is None else (round(float(x), 4) if np.isfinite(x) else None)


def main() -> None:
    df = pd.read_parquet(V4)
    dl = pd.read_parquet(DELTAS, columns=["measurement_record_id"] + DELTA_FEATS)
    if dl["measurement_record_id"].duplicated().any():
        dl = dl.drop_duplicates("measurement_record_id")
    n_before = len(df)
    df = df.merge(dl, on="measurement_record_id", how="left", validate="one_to_one")
    coverage = {
        "anchors": n_before,
        "with_delta_row": int(df["has_prior_measurement"].notna().sum()),
        "join_coverage_pct": round(100 * float(df["has_prior_measurement"].notna().mean()), 2),
        "with_prior_measurement": int((df["has_prior_measurement"] == 1).sum()),
    }

    # ---- design matrices: base vs base+delta ----
    Xb = build_matrix(df)
    Xd = np.hstack([Xb, df[DELTA_FEATS].to_numpy(dtype=float)])

    # ---- never-seen-loco holdout ids (identical to run_loco_holdout) ----
    wes = pd.read_parquet(WES, columns=["measurement_record_id", "locomotive_id"])
    df = df.merge(wes.drop_duplicates("measurement_record_id"), on="measurement_record_id",
                  how="left", validate="one_to_one")
    rng = np.random.default_rng(SEED)
    locos = np.sort(df["locomotive_id"].dropna().unique())
    holdout_ids = set(rng.choice(locos, size=int(len(locos) * 0.20), replace=False))
    ho = df["locomotive_id"].isin(holdout_ids).to_numpy()
    coverage["n_loco_total"] = int(len(locos))
    coverage["n_loco_holdout"] = int(len(holdout_ids))

    te_split = df["split"].eq("test").to_numpy()
    tr_split = df["split"].eq("train").to_numpy()

    out = {
        "task": "phase 4 free-delta ablation (Target B primary; Target A diagnostic)",
        "protocol": "frozen v4 risk_benchmark; B1 config identical to rolling benchmark",
        "delta_features": DELTA_FEATS,
        "coverage": coverage,
        "evaluations": {},
    }

    for target in ("turn", "root"):
        evA, evB = {}, {}
        for H in HORIZONS:
            lab = df[f"{target}_within_{H}d"].to_numpy(dtype=float)
            el = df[f"eligible_{H}d"].to_numpy(dtype=bool)
            ok = np.isfinite(lab)
            # ---- A: frozen split ----
            trm = tr_split & el & ok
            tem = te_split & el & ok
            ytr, yte = lab[trm], lab[tem]
            rowA = {}
            if trm.sum() >= 500 and tem.sum() >= 100 and yte.sum() >= 10:
                p0 = np.full(int(tem.sum()), float(ytr.mean()))
                pb = fit_b1(Xb[trm], ytr, Xb[tem])
                pd_ = fit_b1(Xd[trm], ytr, Xd[tem])
                rowA = {
                    "B0_prevalence": {k: r(v) for k, v in cell(p0, yte).items()},
                    "B1_baseline": {k: r(v) for k, v in cell(pb, yte).items()},
                    "B1_free_deltas": {k: r(v) for k, v in cell(pd_, yte).items()},
                    "delta_lift_capture10": r(
                        (capture_at(pd_, yte, 0.10) or 0) - (capture_at(pb, yte, 0.10) or 0)),
                    "delta_lift_roc_auc": r(
                        (roc_auc(pd_, yte) or 0) - (roc_auc(pb, yte) or 0)),
                }
                if target == "turn":
                    # calibration comparison on the WINNING arm's scores
                    win_is_delta = (roc_auc(pd_, yte) or 0) >= (roc_auc(pb, yte) or 0)
                    win_name = "B1_free_deltas" if win_is_delta else "B1_baseline"
                    Xwin_tr = Xd[trm] if win_is_delta else Xb[trm]
                    ptr_full = fit_b1(Xwin_tr, ytr, Xwin_tr)
                    p_win = pd_ if win_is_delta else pb
                    band = decile_band_fit(ptr_full, ytr)
                    p_dec = decile_band_apply(band, p_win)
                    iso2 = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")
                    iso2.fit(ptr_full, ytr)
                    p_iso = iso2.predict(p_win)
                    rowA["calibration"] = {
                        "arm": win_name,
                        "decile_band": {"ece": r(ece(p_dec, yte)), "brier": r(brier(p_dec, yte)),
                                        "reliability": reliability(p_dec, yte)},
                        "isotonic": {"ece": r(ece(p_iso, yte)), "brier": r(brier(p_iso, yte)),
                                     "reliability": reliability(p_iso, yte)},
                    }
            evA[str(H)] = rowA
            # ---- B: never-seen-loco ----
            trm = (~ho) & el & ok
            tem = ho & el & ok
            ytr, yte = lab[trm], lab[tem]
            rowB = {}
            if trm.sum() >= 500 and tem.sum() >= 100 and yte.sum() >= 20:
                p0 = np.full(int(tem.sum()), float(ytr.mean()))
                pb = fit_b1(Xb[trm], ytr, Xb[tem])
                pd_ = fit_b1(Xd[trm], ytr, Xd[tem])
                rowB = {
                    "B1_baseline": {k: r(v) for k, v in cell(pb, yte).items()},
                    "B1_free_deltas": {k: r(v) for k, v in cell(pd_, yte).items()},
                    "delta_lift_capture10": r(
                        (capture_at(pd_, yte, 0.10) or 0) - (capture_at(pb, yte, 0.10) or 0)),
                    "delta_lift_roc_auc": r(
                        (roc_auc(pd_, yte) or 0) - (roc_auc(pb, yte) or 0)),
                }
            evB[str(H)] = rowB
        out["evaluations"][target] = {"frozen_test_split": evA, "never_seen_loco": evB}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "free_delta_ablation.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    # ---- console summary ----
    print(f"join coverage: {coverage['join_coverage_pct']}% "
          f"({coverage['with_delta_row']}/{coverage['anchors']})")
    for target in ("turn", "root"):
        for ev_name, ev in (("frozen-test", out["evaluations"][target]["frozen_test_split"]),
                            ("loco-holdout", out["evaluations"][target]["never_seen_loco"])):
            for H in HORIZONS:
                row = ev.get(str(H)) or {}
                b1b = row.get("B1_baseline"); b1d = row.get("B1_free_deltas")
                if not b1b:
                    continue
                print(f"{target} {H:>3}d {ev_name:<13} "
                      f"base cap10={b1b['capture10']} roc={b1b['roc_auc']} | "
                      f"+delta cap10={b1d['capture10']} roc={b1d['roc_auc']} | "
                      f"dCap10={row['delta_lift_capture10']} dRoc={row['delta_lift_roc_auc']}")
    cal = out["evaluations"]["turn"]["frozen_test_split"].get("90", {}).get("calibration")
    if cal:
        print(f"calibration[{cal['arm']} @90d turn] decile ECE={cal['decile_band']['ece']} "
              f"Brier={cal['decile_band']['brier']} | isotonic ECE={cal['isotonic']['ece']} "
              f"Brier={cal['isotonic']['brier']}")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
