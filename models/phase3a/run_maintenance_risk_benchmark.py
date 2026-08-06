"""Phase 3A - maintenance-risk benchmark.

Trains simple models (Logistic Regression, Random Forest, XGBoost, CatBoost)
on each eligible horizon cohort and evaluates them like an engineering system.

Question answered: does engineering state predict maintenance realization
better than chance, and if engineers inspect the highest-risk k% of wheels,
what fraction of future turning events are captured?

Metrics (per evaluation contract): PR-AUC (primary), ROC-AUC, Recall@Top-1/5/10%
(Event Capture), precision-at-top, Brier, ECE. Uses a temporal split (train on
earlier measurement times, test on later) to avoid leakage.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "model_datasets" / "v3a"
OUTPUT = ROOT / "models" / "experiments" / "v3a"
HORIZONS = (30, 90, 180, 365)
SEED = 42

FEATURE_COLUMNS = [
    "wsmDia1", "wsmDia2",
    "wsmFlangeThickness1", "wsmFlangeThickness2",
    "wsmRoot1", "wsmRoot2",
    "wsmTireThikness1", "wsmTireThikness2",
    "wsmWheelGauge1", "wsmWheelGauge2",
    "interval_days", "rtis_source_event_count", "rtis_source_event_type_count",
    "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct",
    "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count",
    "wheel_position_1_12", "axle_position_1_6", "wheel_age_days_proxy",
    "days_since_turning", "interval_context_available",
]
CATEGORICAL_COLUMNS = ["LocoType", "wheel_profile_2class", "home_shed",
                       "defect_zone", "defect_division"]


def recall_at_top(y_true, y_prob, top_frac):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    order = np.argsort(-y_prob)
    k = max(1, int(round(top_frac * len(y_true))))
    top = order[:k]
    events_total = int(y_true.sum())
    captured = int(y_true[top].sum())
    recall = captured / events_total if events_total else np.nan
    precision = captured / k if k else np.nan
    return recall, precision, k, events_total, captured


def _fit_label_encoders(df):
    encoders = {}
    for c in CATEGORICAL_COLUMNS:
        if c in df.columns:
            vals = df[c].dropna().astype(str).unique()
            encoders[c] = {v: i for i, v in enumerate(sorted(vals))}
    return encoders


def _encode_categoricals(df, encoders):
    out = df.copy()
    for c, mapping in encoders.items():
        if c in out.columns:
            out[c] = out[c].astype(str).map(mapping).astype(float)
    return out


def _prep_linear(Xtr_enc, Xte_enc):
    from sklearn.preprocessing import StandardScaler, OneHotEncoder
    num_cols = [c for c in FEATURE_COLUMNS if c in Xtr_enc.columns]
    cat_cols = [c for c in CATEGORICAL_COLUMNS if c in Xtr_enc.columns]
    if cat_cols:
        ohe = OneHotEncoder(handle_unknown="ignore")
        ohe.fit(Xtr_enc[cat_cols].astype(str))
        num_tr = Xtr_enc[num_cols].fillna(0.0)
        num_te = Xte_enc[num_cols].fillna(0.0)
        sc = StandardScaler().fit(num_tr)
        import scipy.sparse as sp
        Xtr = sp.hstack([sc.transform(num_tr),
                         ohe.transform(Xtr_enc[cat_cols].astype(str))]).tocsr()
        Xte = sp.hstack([sc.transform(num_te),
                         ohe.transform(Xte_enc[cat_cols].astype(str))]).tocsr()
    else:
        sc = StandardScaler().fit(Xtr_enc.fillna(0.0))
        Xtr = sc.transform(Xtr_enc.fillna(0.0))
        Xte = sc.transform(Xte_enc.fillna(0.0))
    return Xtr, Xte


def train_model(name, Xtr, ytr, Xte):
    if name == "logistic":
        Xtr_p, Xte_p = _prep_linear(Xtr, Xte)
        m = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced",
                               random_state=SEED)
        m.fit(Xtr_p, ytr)
        return lambda df: m.predict_proba(Xte_p)[:, 1]  # noqa: B023
    # Tree-based models: label-encode categoricals, keep NaN for native handling.
    if name == "catboost":
        encoders = _fit_label_encoders(Xtr)
        Xtr_e = _encode_categoricals(Xtr, encoders)
        import catboost as cb
        m = cb.CatBoostClassifier(iterations=300, learning_rate=0.05, depth=6,
                                  nan_mode="Min", verbose=False, random_seed=SEED)
        m.fit(Xtr_e, ytr)
        Xte_e = _encode_categoricals(Xte, encoders)
        return lambda df: m.predict_proba(Xte_e)[:, 1]  # noqa: B023
    encoders = _fit_label_encoders(Xtr)
    Xtr_e = _encode_categoricals(Xtr, encoders)
    Xte_e = _encode_categoricals(Xte, encoders)
    if name == "randomforest":
        m = RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=20,
                                   class_weight="balanced", n_jobs=-1, random_state=SEED)
        m.fit(Xtr_e, ytr)
        return lambda df: m.predict_proba(Xte_e)[:, 1]  # noqa: B023
    if name == "xgboost":
        import xgboost as xgb
        m = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
                              subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                              random_state=SEED, eval_metric="logloss")
        m.fit(Xtr_e, ytr)
        return lambda df: m.predict_proba(Xte_e)[:, 1]  # noqa: B023
    raise ValueError(name)


def binomial_ci(p, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    se = np.sqrt(p * (1 - p) / n)
    return max(0.0, p - z * se), min(1.0, p + z * se)


def evaluate(y_true, y_prob):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    prevalence = float(y_true.mean())
    pr_auc = average_precision_score(y_true, y_prob)
    roc = roc_auc_score(y_true, y_prob)
    lifts = {}
    for frac in (0.01, 0.05, 0.10):
        rec, prec, k, tot, cap = recall_at_top(y_true, y_prob, frac)
        lifts[f"recall_top_{int(frac*100)}pct"] = rec
        lifts[f"precision_top_{int(frac*100)}pct"] = prec
        lifts[f"top_{int(frac*100)}pct_k"] = k
        lifts[f"top_{int(frac*100)}pct_captured"] = cap
    brier = float(brier_score_loss(y_true, y_prob))
    lo, hi = binomial_ci(prevalence, len(y_true))
    for frac in (0.01, 0.05, 0.10):
        key = int(frac * 100)
        recall = lifts[f"recall_top_{key}pct"]
        random_recall = prevalence
        lifts[f"lift_top_{key}pct"] = round(recall / max(random_recall, 1e-9), 3)
    return {
        "n": int(len(y_true)), "pos_rate": prevalence, "pos_rate_ci": [round(lo, 4), round(hi, 4)],
        "pr_auc": round(pr_auc, 4), "roc_auc": round(roc, 4), "brier": round(brier, 4),
        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in lifts.items()},
    }


def main() -> None:
    models = ["logistic", "randomforest", "xgboost", "catboost"]
    report_rows = []
    OUTPUT.mkdir(parents=True, exist_ok=True)

    summary = {"split": "temporal 80/20 by measurement time", "seed": SEED, "models": {}, "horizons": {}}

    for horizon in HORIZONS:
        label_col = f"within_{horizon}d"
        path = DATASET_DIR / f"turn_within_{horizon}d.parquet"
        ds = pd.read_parquet(path)
        ds = ds.dropna(subset=[label_col]).copy()
        y = ds[label_col].astype(int).to_numpy()

        # Temporal split: train on earliest 80% of measurement times, test on latest 20%.
        cutoff = ds["time"].quantile(0.80)
        tr_mask = ds["time"] < cutoff
        te_mask = ~tr_mask

        Xtr = ds.loc[tr_mask, FEATURE_COLUMNS + CATEGORICAL_COLUMNS]
        ytr = y[tr_mask.to_numpy()]
        Xte = ds.loc[te_mask, FEATURE_COLUMNS + CATEGORICAL_COLUMNS]
        yte = y[te_mask.to_numpy()]

        rows_by_model = {}
        for name in models:
            predict = train_model(name, Xtr, ytr, Xte)
            y_prob = predict(Xte)
            ev = evaluate(yte, y_prob)
            ev["model"] = name
            ev["horizon"] = horizon
            ev["test_n"] = int(len(yte))
            rows_by_model[name] = ev
            report_rows.append(ev)
            print(f"  {horizon}d {name:12s} PR={ev['pr_auc']:.4f} ROC={ev['roc_auc']:.4f} "
                  f"R@1%={ev['recall_top_1pct']:.3f} R@5%={ev['recall_top_5pct']:.3f} "
                  f"R@10%={ev['recall_top_10pct']:.3f}")

        summary["horizons"][str(horizon)] = {"test_n": int(len(yte)),
                                             "test_pos_rate": float(yte.mean()),
                                             "models": rows_by_model}

    (OUTPUT / "maintenance_risk_benchmark.json").write_text(
        __import__("json").dumps(summary, indent=2) + "\n", encoding="utf-8")

    pd.DataFrame(report_rows).to_csv(OUTPUT / "maintenance_risk_results.csv", index=False)

    lines = [
        "# Phase 3A - Maintenance Risk Benchmark",
        "",
        "Question: does engineering state predict maintenance realization better than",
        "chance, and what fraction of future turning events are captured by inspecting",
        "the highest-risk wheels?",
        "",
        "Split: temporal 80/20 by measurement time. PR-AUC primary (rare events).",
        "Baseline PR-AUC (random) = test positive rate.",
        "",
        "## Results",
        "",
        "| Horizon | Model | Test n | Pos rate | PR-AUC | ROC-AUC | R@1% | R@5% | R@10% | P@5% | Brier |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in report_rows:
        lines.append(
            f"| {r['horizon']} d | {r['model']} | {r['n']:,} | {r['pos_rate']:.3f} "
            f"| {r['pr_auc']:.4f} | {r['roc_auc']:.4f} | {r['recall_top_1pct']:.3f} "
            f"| {r['recall_top_5pct']:.3f} | {r['recall_top_10pct']:.3f} "
            f"| {r['precision_top_5pct']:.3f} | {r['brier']:.4f} |"
        )
    lines += [
        "",
        "## Reading Recall@Top-k (Event Capture)",
        "",
        "- Recall@Top-5% = if engineers inspect the highest-risk 5% of wheels, the",
        "  fraction of future turning events those wheels contain.",
        "- Random expectation = positive rate (so R@5% should beat ~0.05 for 90d).",
        "- Precision@Top-5% = fraction of the inspected 5% that actually turn, a",
        "  direct measure of inspection workload value.",
        "",
        "## Deterministic caveats",
        "",
        "- Prediction is of **maintenance realization** under partial observability",
        "  (inspections, RTIS exposure, FOIS movement observed; true trigger, workshop",
        "  batching, capacity, operator judgement unobserved).",
        "- It does not claim to recover the latent engineering decision process.",
        "- 365d has the weakest follow-up (see Target Eligibility Matrix), so its",
        "  numbers are least comparable.",
    ]
    (OUTPUT / "maintenance_risk_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
