"""Dataset Validation — engineering and data-science safety checks.

Answers: "Is the dataset safe to train on?" before any modelling.

Checks:
  1. duplicate keys / duplicate rows
  2. wheelset overlap across splits (must be zero)
  3. leakage: no label column may be an X feature
  4. missingness: X must be fully populated (NA sentinels are encoded, not NA)
  5. constants in X (no predictive value)
  6. label sanity: prevalence, censoring, ranges, extreme values
  7. temporal coverage per split (date range)
  8. cardinality of one-hot/frequency columns (no explosion)
  9. feature-feature correlation (top pairs) and feature-label correlation
 10. label-horizon sanity: next labels strictly after interval_end

Emits a validation report JSON with a per-check verdict and an overall verdict.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATASET_DIR = PROJECT_ROOT / "model_datasets" / "v1.0"
DATASET_PATH = DATASET_DIR / "model_dataset_v1.0.parquet"
MANIFEST_PATH = DATASET_DIR / "model_dataset_manifest_v1.0.json"


def _run_checks() -> dict:
    dataset = pd.read_parquet(DATASET_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    roles = manifest["column_roles"]
    x_columns = [c for c, role in roles.items() if role == "feature"]
    y_columns = [c for c, role in roles.items() if role == "label"]
    checks: dict[str, dict] = {}

    # 1. Duplicates.
    dupe_keys = int(dataset.duplicated(["operational_exposure_id"]).sum())
    checks["duplicate_keys"] = {"passed": dupe_keys == 0, "duplicate_rows": dupe_keys}

    # 2. Wheelset overlap across splits.
    wheelset_split = dataset.groupby("wheelset_equipment_id")["split"].nunique()
    overlap = int((wheelset_split > 1).sum())
    checks["wheelset_split_overlap"] = {"passed": overlap == 0, "wheelsets_spanning_splits": overlap}

    # 3. Leakage: label columns must not be X features.
    leaked = [c for c in y_columns if c in x_columns]
    checks["label_leakage"] = {"passed": not leaked, "leaked_columns": leaked}

    # 4. Missingness in X.
    x_na = int(dataset[x_columns].isna().sum().sum())
    checks["x_missingness"] = {"passed": x_na == 0, "na_cells_in_x": x_na}

    # 5. Constants in X.
    constants = [c for c in x_columns if dataset[c].nunique(dropna=True) <= 1]
    checks["constant_columns"] = {"passed": not constants, "constant_columns": constants}

    # 6. Label sanity.
    label_stats: dict[str, dict] = {}
    label_ok = True
    for col in y_columns:
        s = dataset[col]
        stats = {"n": int(s.notna().sum()), "null_pct": round(float(s.isna().mean() * 100), 2)}
        if s.dtype.kind in "fbiu":
            stats.update({"mean": round(float(s.mean()), 4), "std": round(float(s.std()), 4), "min": round(float(s.min()), 4), "max": round(float(s.max()), 4)})
        label_stats[col] = stats
    # Sanity: turning positive rate plausible (2-3% of measurements; interval-level 1-3%).
    turn_rate = float(dataset["next_interval_turning_flag"].mean())
    if not (0.001 < turn_rate < 0.1):
        label_ok = False
    # Censoring: time_to_next_turning should be censored for the large majority.
    cens = float(dataset["censored_flag"].mean())
    if not (0.5 < cens < 1.0):
        label_ok = False
    checks["label_sanity"] = {"passed": label_ok, "labels": label_stats, "turning_positive_rate": round(turn_rate, 4), "censored_rate": round(cens, 4)}

    # 7. Temporal coverage per split (informational: grouped temporal splits are
    #    expected to overlap in wall-clock time; the guarantee is no wheelset overlap).
    checks["temporal_coverage"] = {"passed": True, "note": "overlap expected for grouped temporal split", **dataset.groupby("split")["interval_end_timestamp"].agg(["min", "max", "count"]).astype(str).to_dict()}

    # 8. Cardinality: one-hot columns expected exactly 2 levels (0/1); frequency
    #    columns are continuous and excluded.
    one_hot_cols = [c for c in x_columns if "__" in c and not c.endswith("__freq")]
    max_levels = max((int(dataset[c].nunique(dropna=True)) for c in one_hot_cols), default=0)
    cardinality_ok = max_levels <= 2
    checks["cardinality"] = {"passed": cardinality_ok, "one_hot_columns": len(one_hot_cols), "max_levels_in_one_hot_col": max_levels}

    # 9. Correlations (informational; collinearity is reported, not a failure for baselines).
    sample = dataset[x_columns + y_columns].sample(min(len(dataset), 60_000), random_state=42)
    corr = sample.corr(numeric_only=True)
    # top feature-feature correlations
    mask = ~np.eye(len(corr), dtype=bool)
    ff = corr.where(mask).abs().unstack().dropna().sort_values(ascending=False)
    seen = set()
    ff_pairs = []
    for (a, b), v in ff.items():
        key = tuple(sorted((str(a), str(b))))
        if key in seen:
            continue
        seen.add(key)
        ff_pairs.append((key[0], key[1], round(float(v), 3)))
        if len(ff_pairs) >= 10:
            break

    checks["correlations"] = {
        "passed": True,
        "top_feature_feature": ff_pairs,
        "feature_label_abs_top5": {
            str(col): round(float(v), 3)
            for col, v in sample[x_columns].apply(lambda s: s.corr(sample["next_interval_dia_delta_mm"])).abs().sort_values(ascending=False).head(5).items()
        },
    }

    # 10. Label horizon sanity: next-interval timestamp strictly after interval_end where present.
    horizon_ok = int((dataset["next_interval_end_timestamp"] <= dataset["interval_end_timestamp"]).sum()) == 0
    checks["label_horizon"] = {"passed": horizon_ok, "rows_violating_horizon": int((dataset["next_interval_end_timestamp"] <= dataset["interval_end_timestamp"]).sum())}

    overall = all(check.get("passed", False) for check in checks.values())
    return {"verdict": "PASS" if overall else "FAIL", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "checks": checks, "dataset_version": manifest["dataset_version"]}


if __name__ == "__main__":
    report = _run_checks()
    out = DATASET_DIR / "validation_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"VERDICT: {report['verdict']}")
    for name, check in report["checks"].items():
        print(f"  [{'PASS' if check.get('passed') else 'FAIL'}] {name}: {check}")
