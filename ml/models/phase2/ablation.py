"""WS5 — family-level ablation on the v2.0 dataset (grouped splits).

Three arms per model (lightgbm champion + linear baseline):
  1. Forward selection: greedily add the family that most improves test RMSE.
  2. Leave-one-out: full 8-family set minus each family (drop columns).
  3. Availability-normalized: the LOO delta restricted to rows where the removed
     family is actually present (answers "how much does this family help where
     it is available", removing the pre-2023 presence confound).

Trees get native-NaN (missing family = all-NaN columns). Linear/RF get
family-median imputation + one missingness indicator per family, and dropping a
family drops its columns AND its indicator (columns come from families.py).

Outputs: per-arm CSV + a consolidated report markdown.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models import evaluate  # noqa: E402
from models.phase2.families import FAMILY_ORDER, feature_families  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
EXPERIMENTS_ROOT = PROJECT_ROOT / "models" / "experiments" / "v2"
OUT_DIR = EXPERIMENTS_ROOT / "ablation"
REGRESSION_LABEL = "next_interval_dia_delta_mm"
SEED = 42
N_ESTIMATORS = 300


def _estimator(model_name: str, seed: int):
    if model_name == "lightgbm":
        import lightgbm as lgb
        return lgb.LGBMRegressor(n_estimators=N_ESTIMATORS, learning_rate=0.05,
                                 num_leaves=63, subsample=0.8, colsample_bytree=0.8,
                                 n_jobs=-1, random_state=seed, verbosity=-1)
    if model_name == "linear":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LinearRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        return Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                         ("scale", StandardScaler()), ("reg", LinearRegression())])
    raise ValueError(model_name)


def _train_eval(df, x_cols, model_name, fams):
    tr, va, te = (df[df["split"] == s] for s in ("train", "val", "test"))
    ytr = tr[REGRESSION_LABEL].values
    yte = te[REGRESSION_LABEL].values
    Xtr, Xte = tr[x_cols].copy(), te[x_cols].copy()

    if model_name == "linear":
        present = [f for f in FAMILY_ORDER if any(c in x_cols for c in fams[f])]
        ind_tr = pd.DataFrame({f"miss_{f}": tr[fams[f]].isna().any(axis=1).astype(int) for f in present})
        ind_te = pd.DataFrame({f"miss_{f}": te[fams[f]].isna().any(axis=1).astype(int) for f in present})
        Xtr = pd.concat([Xtr, ind_tr], axis=1)
        Xte = pd.concat([Xte, ind_te], axis=1)

    est = _estimator(model_name, SEED)
    est.fit(Xtr, ytr)
    return evaluate.regression_metrics(yte, est.predict(Xte))


def main() -> None:
    df = pd.read_parquet(DATASET_PATH)
    fams = feature_families()
    all_cols = [c for cols in fams.values() for c in cols]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # availability of each family in test (fraction of rows with >=1 non-null;
    # probe gated v2 families on their genuinely-gated column, not legacy mixes)
    probe = {"exposure_v2": "interval_distance_km", "physics_v2": "wear_per_1000km_s1"}
    te_mask = df["split"] == "test"
    avail = {}
    for f in FAMILY_ORDER:
        cols = [probe[f]] if f in probe else [c for c in fams[f]]
        avail[f] = float(df.loc[te_mask, cols].notna().any(axis=1).mean())

    rows_forward, rows_loo, rows_avail = [], [], []

    for model_name in ("lightgbm", "linear"):
        base = _train_eval(df, all_cols, model_name, fams)
        print(f"{model_name}: full-set RMSE={base['rmse']:.3f}")

        # --- Leave-one-out ---
        for fam in FAMILY_ORDER:
            reduced = [c for c in all_cols if c not in fams[fam]]
            m = _train_eval(df, reduced, model_name, fams)
            rows_loo.append({"model": model_name, "removed": fam, "rmse": m["rmse"],
                             "mae": m["mae"], "delta_rmse": m["rmse"] - base["rmse"],
                             "full_rmse": base["rmse"]})

        # --- Forward selection ---
        from sklearn.dummy import DummyRegressor
        tr_full = df[df["split"] == "train"]
        te_full = df[df["split"] == "test"]
        dummy = DummyRegressor(strategy="mean").fit(
            tr_full[[REGRESSION_LABEL]], tr_full[REGRESSION_LABEL].values)
        dummy_rmse = float(evaluate.regression_metrics(
            te_full[REGRESSION_LABEL].values,
            dummy.predict(te_full[[REGRESSION_LABEL]]))["rmse"])
        selected: list[str] = []
        current_rmse = None
        while len(selected) < len(FAMILY_ORDER):
            best_fam, best_m, best_delta = None, None, None
            for fam in FAMILY_ORDER:
                if fam in selected:
                    continue
                selected_cols = [c for f in selected for c in fams[f]] + fams[fam]
                m = _train_eval(df, selected_cols, model_name, fams)
                delta = (dummy_rmse - m["rmse"]) if current_rmse is None else (current_rmse - m["rmse"])
                if best_m is None or delta > best_delta:
                    best_fam, best_m, best_delta = fam, m, delta
            selected.append(best_fam)
            current_rmse = best_m["rmse"]
            rows_forward.append({"model": model_name, "step": len(selected), "added": best_fam,
                                 "rmse": best_m["rmse"], "mae": best_m["mae"],
                                 "delta_rmse": best_delta, "cumulative_delta_rmse": base["rmse"] - best_m["rmse"]})
            print(f"  {model_name} forward +{best_fam}: RMSE={best_m['rmse']:.3f} "
                  f"(d={best_delta:+.3f})")

        # --- Availability-normalized LOO (restricted to rows where family present) ---
        te = df[te_mask]
        # Probe presence on the genuinely-gated new columns only (some families mix
        # legacy always-present columns with v2-gated ones; any(axis=1) would short-circuit).
        probe = {"exposure_v2": "interval_distance_km", "physics_v2": "wear_per_1000km_s1"}
        for fam in FAMILY_ORDER:
            if fam in probe:
                present = te[probe[fam]].notna()
            else:
                present = te[[c for c in fams[fam]]].notna().any(axis=1)
            if present.sum() < 100:
                rows_avail.append({"model": model_name, "removed": fam, "n_present": int(present.sum()),
                                   "full_rmse": np.nan, "loo_rmse": np.nan, "delta_rmse": np.nan})
                continue
            sub = te[present]
            x_full = [c for c in all_cols]
            x_red = [c for c in all_cols if c not in fams[fam]]
            m_full = _train_eval_subset(df, sub.index, x_full, model_name, fams)
            m_red = _train_eval_subset(df, sub.index, x_red, model_name, fams)
            rows_avail.append({"model": model_name, "removed": fam, "n_present": int(present.sum()),
                               "full_rmse": m_full["rmse"], "loo_rmse": m_red["rmse"],
                               "delta_rmse": m_red["rmse"] - m_full["rmse"]})

    pd.DataFrame(rows_forward).to_csv(OUT_DIR / "forward_selection.csv", index=False)
    pd.DataFrame(rows_loo).to_csv(OUT_DIR / "leave_one_out.csv", index=False)
    pd.DataFrame(rows_avail).to_csv(OUT_DIR / "availability_normalized.csv", index=False)
    pd.DataFrame([{"family": f, "test_availability": a} for f, a in avail.items()]).to_csv(
        OUT_DIR / "family_availability_test.csv", index=False)

    _report(avail=avail)
    print(f"-> {OUT_DIR}: forward_selection.csv, leave_one_out.csv, "
          f"availability_normalized.csv, ablation_report.md")


def _train_eval_subset(df, idx, x_cols, model_name, fams):
    """Train on train rows, evaluate ONLY on the given test-subset rows."""
    tr = df[df["split"] == "train"]
    Xtr = tr[x_cols].copy()
    ytr = tr[REGRESSION_LABEL].values
    sub = df.loc[idx]
    Xte = sub[x_cols].copy()
    yte = sub[REGRESSION_LABEL].values
    if model_name == "linear":
        present = [f for f in FAMILY_ORDER if any(c in x_cols for c in fams[f])]
        ind_tr = pd.DataFrame({f"miss_{f}": tr[fams[f]].isna().any(axis=1).astype(int) for f in present})
        ind_te = pd.DataFrame({f"miss_{f}": sub[fams[f]].isna().any(axis=1).astype(int) for f in present})
        Xtr = pd.concat([Xtr, ind_tr], axis=1)
        Xte = pd.concat([Xte, ind_te], axis=1)
    est = _estimator(model_name, SEED)
    est.fit(Xtr, ytr)
    return evaluate.regression_metrics(yte, est.predict(Xte))


def _report(avail=None) -> None:
    loo = pd.read_csv(OUT_DIR / "leave_one_out.csv")
    fwd = pd.read_csv(OUT_DIR / "forward_selection.csv")
    lines = [
        "# WS5 Ablation — family-level (v2.0, grouped test)",
        "",
        "## Leave-one-out (RMSE delta vs full set)",
        "",
        "| model | removed family | full RMSE | LOO RMSE | ΔRMSE |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for _, r in loo.sort_values("delta_rmse", ascending=False).iterrows():
        lines.append(f"| {r['model']} | {r['removed']} | {r['full_rmse']:.3f} | "
                     f"{r['rmse']:.3f} | {r['delta_rmse']:+.3f} |")
    lines += [
        "",
        "## Forward selection (lightgbm)",
        "",
        "| step | added family | RMSE | Δ step | vs full-set |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for _, r in fwd[fwd["model"] == "lightgbm"].iterrows():
        lines.append(f"| {r['step']} | {r['added']} | {r['rmse']:.3f} | {r['delta_rmse']:+.3f} | "
                     f"{r['cumulative_delta_rmse']:+.3f} |")
    lines += [
        "",
        "## Forward selection (linear)",
        "",
        "| step | added family | RMSE | Δ step | vs full-set |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for _, r in fwd[fwd["model"] == "linear"].iterrows():
        lines.append(f"| {r['step']} | {r['added']} | {r['rmse']:.3f} | {r['delta_rmse']:+.3f} | "
                     f"{r['cumulative_delta_rmse']:+.3f} |")
    lines += [
        "",
        "## Test availability (rows with the family present)",
        "",
        "| family | availability |",
        "| --- | ---: |",
    ]
    for f in FAMILY_ORDER:
        lines.append(f"| {f} | {avail[f]:.3f} |")
    lines += [
        "",
        "## Caveats",
        "",
        "- LOO deltas are averaged over all test rows; families present only post-2023",
        "  (exposure_v2, physics_v2) show diluted deltas. See availability_normalized.csv",
        "  for the same deltas restricted to rows where the family is present.",
        "- For trees, a dropped family becomes all-NaN columns; for linear, its columns",
        "  and its missingness indicator are both removed.",
    ]
    (OUT_DIR / "ablation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
