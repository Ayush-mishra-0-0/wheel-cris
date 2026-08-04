"""V1.2 label-cleanup audit: quantify sentinel labels in the v1.1 model dataset.

Loads the immutable v1.1 model dataset (all splits), joins the two measurements
that define the regression label (next interval end - next interval start) back
to bronze wheel_measurements, and characterizes label sentinels:

  label = wsmDia1[next_interval_end_measurement_id]
          - wsmDia1[interval_end_measurement_id]

Two sentinel sources are audited:
  A) impossible label magnitude   (|delta| > threshold)
  B) non-physical endpoint diameter (wsmDia1 outside [600, 1300] on either side)

Cross-tab shows whether rule B subsumes rule A at various thresholds, which
decides the V1.2 quarantine rule.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DSET = ROOT / "model_datasets" / "v1.1" / "model_dataset_v1.1.parquet"
MEAS = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUT = ROOT / "models" / "experiments" / "v1.2"
OUT.mkdir(parents=True, exist_ok=True)

PHYS_LO, PHYS_HI = 600.0, 1300.0
THRESHOLDS = [20.0, 30.0, 50.0, 80.0, 100.0, 200.0, 500.0]


def main():
    df = pd.read_parquet(DSET, columns=[
        "split", "operational_exposure_id", "interval_end_measurement_id",
        "next_interval_end_measurement_id", "next_interval_dia_delta_mm",
        "next_interval_root_delta_mm", "home_shed", "turning_indicator_raw",
        "next_interval_turning_flag", "wheelset_equipment_id",
        "locomotive_number", "LocoType",
    ])
    meas = pd.read_parquet(MEAS, columns=["wsmId", "wsmDia1", "wsmDia2"])

    m_end = meas.set_index("wsmId").loc[df["interval_end_measurement_id"]]
    m_nxt = meas.set_index("wsmId").loc[df["next_interval_end_measurement_id"]]
    df["end_dia1"] = m_end["wsmDia1"].to_numpy()
    df["end_dia2"] = m_end["wsmDia2"].to_numpy()
    df["next_dia1"] = m_nxt["wsmDia1"].to_numpy()
    df["next_dia2"] = m_nxt["wsmDia2"].to_numpy()

    rep = {"rows_total": int(len(df))}
    for sp in ["train", "val", "test"]:
        d = df[df["split"] == sp]
        y = d["next_interval_dia_delta_mm"]
        rep[sp] = {
            "n": int(len(d)),
            "min": float(y.min()), "max": float(y.max()),
            "p99": float(y.quantile(0.99)), "p999": float(y.quantile(0.999)),
            "n_abs_gt_100": int((y.abs() > 100).sum()),
            "n_abs_gt_50": int((y.abs() > 50).sum()),
        }

    # ---- Rule B: non-physical endpoint diameter on either side ----
    b1 = (df["end_dia1"] < PHYS_LO) | (df["end_dia1"] > PHYS_HI) | \
         (df["next_dia1"] < PHYS_LO) | (df["next_dia1"] > PHYS_HI)
    rep["rule_B_phys_600_1300"] = {
        "any_side1_rows": int(b1.sum()),
        "frac_of_rows": float(b1.mean()),
        "by_split": {sp: int(b1[df["split"] == sp].sum()) for sp in ["train", "val", "test"]},
    }

    # ---- Rule A: label-magnitude thresholds, and overlap with rule B ----
    cross = []
    for t in THRESHOLDS:
        a = df["next_interval_dia_delta_mm"].abs() > t
        row = {
            "threshold_mm": t,
            "n_abs_gt": int(a.sum()),
            "frac": float(a.mean()),
            "n_also_phys_sentinel": int((a & b1).sum()),
            "n_phys_ok": int((a & ~b1).sum()),
        }
        cross.append(row)
        rep[f"rule_A_abs_gt_{t:g}"] = row
    cross_df = pd.DataFrame(cross)

    # ---- Profile rows that violate rule A (|label|>100) but pass rule B ----
    a100 = df["next_interval_dia_delta_mm"].abs() > 100
    keep = df[a100 & ~b1].copy()
    rep["rule_A_gt_100_but_phys_ok"] = {
        "n": int(len(keep)),
        "label_min_max": [float(keep["next_interval_dia_delta_mm"].min()),
                          float(keep["next_interval_dia_delta_mm"].max())],
        "end_dia1_min_max": [float(keep["end_dia1"].min()), float(keep["end_dia1"].max())],
        "next_dia1_min_max": [float(keep["next_dia1"].min()), float(keep["next_dia1"].max())],
        "by_shed": keep["home_shed"].value_counts().head(10).to_dict(),
        "has_turning_label": int(keep["next_interval_turning_flag"].sum()),
        "n_neg": int((keep["next_interval_dia_delta_mm"] < 0).sum()),
    }

    # ---- RMSE contribution of sentinels (to show why cleanup matters) ----
    y = df["next_interval_dia_delta_mm"]
    for t in THRESHOLDS:
        a = y.abs() > t
        rmse_all = float(np.sqrt(np.mean(y ** 2)))
        rmse_clean = float(np.sqrt(np.mean(y[~a] ** 2)))
        rep.setdefault("rmse_sensitivity", []).append(
            {"threshold_mm": t, "rmse_all": rmse_all,
             "rmse_excl_sentinel": rmse_clean,
             "mse_from_sentinels_pct": float(
                 100 * (np.mean(y ** 2) - np.mean(y[~a] ** 2)) / np.mean(y ** 2))})

    with open(OUT / "sentinel_audit.json", "w") as fh:
        json.dump(rep, fh, indent=2, default=str)
    print(json.dumps(rep, indent=2, default=str))

    cross_df.to_csv(OUT / "sentinel_audit_thresholds.csv", index=False)
    df[a100].to_csv(OUT / "sentinel_rows_gt100.csv", index=False)
    print("\nwrote:", OUT)


if __name__ == "__main__":
    main()
