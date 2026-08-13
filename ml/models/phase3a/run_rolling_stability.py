"""Phase 3A - rolling stability of the maintenance-risk benchmark.

The headline result (inspect top-5% -> capture ~48% of near-term turnings) must
be stable across time cutoffs, not a single-split artefact. This module
evaluates the XGBoost model on successive rolling time windows:

    for each cutoff c (e.g. 60/70/80/90th percentile of time):
        train on states before cutoff
        test  on states in a following window
        record PR-AUC, ROC-AUC, Recall@Top-1/5/10%, Brier, ECE

Output: mean +/- SD across cutoffs (the robustness statement), plus per-cutoff
rows, so the 48% number carries a stability band.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT / "model_datasets" / "v3a"
OUTPUT = ROOT / "models" / "experiments" / "v3a"
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


def _recall_at_top(y_true, y_prob, top_frac):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    order = np.argsort(-y_prob)
    k = max(1, int(round(top_frac * len(y_true))))
    captured = int(y_true[order[:k]].sum())
    events = int(y_true.sum())
    return captured / events if events else np.nan


def _eval(y_true, y_prob):
    from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    return {
        "n": int(len(y_true)),
        "pos_rate": float(y_true.mean()),
        "pr_auc": round(average_precision_score(y_true, y_prob), 4),
        "roc_auc": round(roc_auc_score(y_true, y_prob), 4),
        "recall_top_1pct": round(_recall_at_top(y_true, y_prob, 0.01), 4),
        "recall_top_5pct": round(_recall_at_top(y_true, y_prob, 0.05), 4),
        "recall_top_10pct": round(_recall_at_top(y_true, y_prob, 0.10), 4),
        "brier": round(float(brier_score_loss(y_true, y_prob)), 4),
    }


def _train_xgb(Xtr, ytr, Xte):
    import xgboost as xgb
    encoders = _fit_label_encoders(Xtr)
    Xtr_e = _encode_categoricals(Xtr, encoders)
    Xte_e = _encode_categoricals(Xte, encoders)
    m = xgb.XGBClassifier(n_estimators=300, learning_rate=0.05, max_depth=6,
                          subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                          random_state=SEED, eval_metric="logloss")
    m.fit(Xtr_e, ytr)
    return m.predict_proba(Xte_e)[:, 1]


def main() -> None:
    horizon = 90
    label_col = f"within_{horizon}d"
    ds = pd.read_parquet(DATASET_DIR / f"turn_within_{horizon}d.parquet")
    ds = ds.dropna(subset=[label_col]).copy()
    y = ds[label_col].astype(int).to_numpy()

    timeq = ds["time"].sort_values()
    cutoffs = [timeq.quantile(q) for q in (0.55, 0.65, 0.75, 0.85)]
    test_width = 0.10  # test on the 10% window following each cutoff

    rows = []
    for ci, cutoff in enumerate(cutoffs):
        tr_mask = ds["time"] < cutoff
        te_mask = (ds["time"] >= cutoff) & (ds["time"] < timeq.quantile(min(1.0, 0.55 + (ci + 1) * 0.10)))
        Xtr = ds.loc[tr_mask, FEATURE_COLUMNS + CATEGORICAL_COLUMNS]
        ytr = y[tr_mask.to_numpy()]
        Xte = ds.loc[te_mask, FEATURE_COLUMNS + CATEGORICAL_COLUMNS]
        yte = y[te_mask.to_numpy()]
        if len(yte) < 2000 or yte.sum() < 30:
            continue
        y_prob = _train_xgb(Xtr, ytr, Xte)
        ev = _eval(yte, y_prob)
        ev["cutoff"] = str(cutoff.date())
        rows.append(ev)
        print(f"  cutoff {str(cutoff.date())}  n={ev['n']:,} pos={ev['pos_rate']:.3f} "
              f"PR={ev['pr_auc']:.4f} R@5%={ev['recall_top_5pct']:.3f}")

    df_rows = pd.DataFrame(rows)
    summary = {}
    for metric in ["pr_auc", "roc_auc", "recall_top_1pct", "recall_top_5pct",
                   "recall_top_10pct", "brier"]:
        vals = df_rows[metric].to_numpy()
        summary[metric] = {"mean": round(float(vals.mean()), 4),
                           "sd": round(float(vals.std()), 4),
                           "min": round(float(vals.min()), 4),
                           "max": round(float(vals.max()), 4)}

    out = {"horizon_days": horizon, "model": "xgboost", "cutoffs": rows, "summary": summary}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "rolling_stability_90d.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Rolling stability - maintenance risk ({horizon}d, XGBoost)",
        "",
        "Robustness of the headline capture result across time cutoffs: each row is a",
        "model trained on data before the cutoff and tested on the following 10% window.",
        "",
        "| cutoff | test n | pos rate | PR-AUC | ROC-AUC | R@1% | R@5% | R@10% | Brier |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        lines.append(f"| {r['cutoff']} | {r['n']:,} | {r['pos_rate']:.3f} | {r['pr_auc']:.4f} "
                     f"| {r['roc_auc']:.4f} | {r['recall_top_1pct']:.3f} "
                     f"| {r['recall_top_5pct']:.3f} | {r['recall_top_10pct']:.3f} | {r['brier']:.4f} |")
    lines += ["", "## Stability band (mean +/- SD across cutoffs)", ""]
    for metric, s in summary.items():
        lines.append(f"- {metric}: {s['mean']:.4f} +/- {s['sd']:.4f} (min {s['min']:.4f}, max {s['max']:.4f})")
    lines += [
        "",
        "## Interpretation",
        "",
        "- A tight band around Recall@Top-5% (~48%) means the capture claim is robust,",
        "  not a lucky split.",
        "- Wide bands -> flag which periods the model struggles on (e.g. data drift).",
    ]
    (OUTPUT / "rolling_stability_90d.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
