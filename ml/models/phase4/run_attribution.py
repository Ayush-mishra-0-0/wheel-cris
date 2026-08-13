"""Phase 4 - per-wheel attribution (plan section 9, Stage 4-D).

Fits the production candidate (C1 XGBoost) point-in-time at the most recent
cutoff for both targets at 90 days, scores the trailing-window inspections,
and computes SHAP attribution per wheel. Outputs are "likely contributors" /
model attribution - never "cause".

Design (same point-in-time rules as the rolling benchmark):
  * T = most recent monthly cutoff (production "as of today").
  * train rows = t < T with label determinable at T.
  * score rows = t in (T-step, T] with static (full-hindsight) eligibility.
  * SHAP TreeExplainer on the exact scaled matrix used at predict time.
  * Risk level from score relative to training prevalence; reliability band
    from the score-decile empirical event rate on the training set.

Output: models/experiments/v4/wheel_attribution.parquet + wheel_attribution.json
        (metadata + summary)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_rolling_risk_benchmark import (  # noqa: E402
    NUM_FEATS, CAT_FEATS, LIMIT_ROOT, SEED, build_matrix,
)

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "model_datasets" / "v4" / "risk_benchmark.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v4"
STEP = 30
HORIZON = 90

# feature prefix -> human-readable contributor label
LABELS = {
    "wsmRoot": "Root margin",
    "root": "Root margin",
    "wsmDia": "Diameter state",
    "wsmFlangeThickness": "Flange thickness",
    "wsmWheelGauge": "Wheel gauge",
    "days_since_turning": "Days since last turning",
    "wheel_age": "Wheel age",
    "days_since_last_inspection": "Inspection recency",
    "days_since_segment_start": "Lifecycle segment progress",
    "inspection_count": "Inspection history",
    "km_last": "Exposure (km)",
    "km_30d": "Exposure (km)",
    "km_90d": "Exposure (km)",
    "km_180d": "Exposure (km)",
    "rtis": "RTIS event coverage",
    "maintenance_jobcard": "Maintenance history",
    "home_shed": "Home shed",
    "lifecycle_segment_id": "Lifecycle segment",
    "wheel_position": "Wheel position",
    "axle_position": "Axle position",
    "defect_zone": "Defect zone",
    "defect_division": "Defect division",
    "wheel_profile_2class": "Wheel profile",
    "LocoType": "Loco type",
}

CONST_LABELS = ["Bias", "Intercept"]


def human_label(feat: str) -> str:
    for k, v in LABELS.items():
        if k in feat:
            return v
    return feat.replace("_", " ").title()


def main() -> None:
    df = pd.read_parquet(V4)
    wes = pd.read_parquet(WES, columns=[
        "wheelset_equipment_id", "measurement_record_id", "measurement_timestamp",
        "turning_record_at_measurement", "wsmRoot1", "wsmRoot2",
        "wsmRoot1_quality", "wsmRoot2_quality", "locomotive_id"])

    loco_map = wes.drop_duplicates("measurement_record_id")[
        ["measurement_record_id", "locomotive_id"]]
    df = df.merge(loco_map, on="measurement_record_id", how="left")

    # ---- point-in-time event structures ----
    r1 = wes["wsmRoot1"].to_numpy(dtype=float); r2 = wes["wsmRoot2"].to_numpy(dtype=float)
    q1 = wes["wsmRoot1_quality"].eq("OBSERVED_VALID").to_numpy()
    q2 = wes["wsmRoot2_quality"].eq("OBSERVED_VALID").to_numpy()
    wes["_root"] = np.where(q1 & q2, (r1 + r2) / 2.0, np.where(q1, r1, np.where(q2, r2, np.nan)))
    wes["_turn"] = wes["turning_record_at_measurement"].eq(1).to_numpy()
    wes = wes.sort_values(["wheelset_equipment_id", "measurement_timestamp"]).reset_index(drop=True)
    wes["_t"] = pd.to_datetime(wes["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    wes["_eq"] = wes["wheelset_equipment_id"].astype("int64").to_numpy()

    eq_groups = wes.groupby("_eq", sort=False).groups
    eq_times, eq_root, eq_turn = {}, {}, {}
    for eq, idx in eq_groups.items():
        idx = idx.to_numpy()
        ts = wes["_t"].to_numpy()[idx]; rt = wes["_root"].to_numpy()[idx]
        tn = wes["_turn"].to_numpy()[idx]
        order = np.argsort(ts, kind="mergesort")
        eq_times[int(eq)] = ts[order]; eq_root[int(eq)] = rt[order]; eq_turn[int(eq)] = tn[order]

    t0 = pd.to_datetime(df["measurement_timestamp"]).to_numpy(dtype="datetime64[us]")
    eq = df["wheelset_equipment_id"].astype("int64").to_numpy()
    first_root = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    first_turn = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    obs_end_full = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    for i in range(len(df)):
        e = int(eq[i]); t = t0[i]
        ts = eq_times.get(e)
        if ts is None or ts.size == 0:
            continue
        j = np.searchsorted(ts, t, side="right")
        if j >= ts.size:
            continue
        obs_end_full[i] = ts[-1]
        rt = eq_root[e][j:]; tn = eq_turn[e][j:]; tsj = ts[j:]
        rk = np.flatnonzero(rt > LIMIT_ROOT)
        if rk.size:
            first_root[i] = tsj[rk[0]]
        tk = np.flatnonzero(tn)
        if tk.size:
            first_turn[i] = tsj[tk[0]]

    # most recent monthly cutoff
    tmin = pd.to_datetime(df["measurement_timestamp"]).min()
    tmax = pd.to_datetime(df["measurement_timestamp"]).max()
    cutoffs = pd.date_range(start=tmin + pd.Timedelta(days=180), end=tmax, freq=f"{STEP}D")
    T = cutoffs[-1]
    Tn = np.datetime64(T, "us")

    # obs end as-of T (per equipment)
    obs_asof = np.full(len(df), np.datetime64("NaT"), dtype="datetime64[us]")
    for e, ts in eq_times.items():
        if ts.size == 0:
            continue
        m = eq == e
        if not m.any():
            continue
        j = np.searchsorted(ts, Tn, side="right") - 1
        if j >= 0:
            obs_asof[m] = ts[j]

    Xall = build_matrix(df)
    ev_t = {"root": first_root, "turn": first_turn}
    full_hindsight = (obs_end_full - t0) >= np.timedelta64(HORIZON, "D")

    # ---- fit one model per target at HORIZON, score trailing window ----
    Xallf = np.nan_to_num(Xall, nan=0.0)
    sc_full = StandardScaler().fit(Xallf)
    Xalls = sc_full.transform(Xallf)
    feat_names = NUM_FEATS + list(pd.get_dummies(df[CAT_FEATS].astype(str),
                                                dummy_na=True).columns)
    assert len(feat_names) == Xalls.shape[1], f"{len(feat_names)} != {Xalls.shape[1]}"

    cards = []
    meta = {"task": "phase 4 per-wheel attribution (Stage 4-D)",
            "cutoff": str(T.date()), "horizon_days": HORIZON,
            "targets": {}}

    for target in ("root", "turn"):
        ev = ev_t[target]
        in_win = (ev != np.datetime64("NaT")) & ((ev - t0) <= np.timedelta64(HORIZON, "D"))
        y_true = in_win.astype(float)
        full_by_T = (obs_asof - t0) >= np.timedelta64(HORIZON, "D")
        event_by_T = in_win & (ev <= Tn)
        known = full_by_T | event_by_T
        tr_mask = (t0 < Tn) & known
        # production scoring: ALL trailing-window rows, whatever is knowable now
        sc_mask = (t0 > Tn - np.timedelta64(STEP, "D")) & (t0 <= Tn)

        ytr = y_true[tr_mask]
        xgb = XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                            subsample=0.9, colsample_bytree=0.9, random_state=SEED,
                            n_jobs=-1, tree_method="hist", eval_metric="logloss")
        xgb.fit(Xalls[tr_mask], ytr)
        prev = float(ytr.mean())

        p_tr = xgb.predict_proba(Xalls[tr_mask])[:, 1]
        bins = np.percentile(p_tr, np.arange(0, 101, 10))  # decile bands
        dec = np.clip(np.digitize(p_tr, bins[1:-1]), 0, 9)
        bin_rate = [float(ytr[dec == i].mean()) if (dec == i).sum() else None
                    for i in range(10)]

        p_sc = xgb.predict_proba(Xalls[sc_mask])[:, 1]
        explainer = shap.TreeExplainer(xgb)
        sh = explainer.shap_values(Xalls[sc_mask])
        idx = np.where(sc_mask)[0]
        n = len(idx)
        contrib = []
        for j in range(n):
            vals = sh[j]
            top = np.argsort(-np.abs(vals))[:5]
            contrib.append([{"feature": feat_names[k],
                             "label": human_label(feat_names[k]),
                             "shap": round(float(vals[k]), 5)}
                            for k in top])

        out = pd.DataFrame({
            "measurement_record_id": df["measurement_record_id"].to_numpy()[idx],
            "wheelset_equipment_id": df["wheelset_equipment_id"].to_numpy()[idx],
            "locomotive_id": df["locomotive_id"].to_numpy()[idx],
            "measurement_timestamp": pd.to_datetime(df["measurement_timestamp"].to_numpy()[idx]),
            "wsmRoot_mean": df["wsmRoot_mean"].to_numpy(dtype=float)[idx],
            "wsmDia_mean": df["wsmDia_mean"].to_numpy(dtype=float)[idx],
            "wsmFlangeThickness_mean": df["wsmFlangeThickness_mean"].to_numpy(dtype=float)[idx],
            "wsmWheelGauge_mean": df["wsmWheelGauge_mean"].to_numpy(dtype=float)[idx],
            "prob": p_sc,
            "risk": ["HIGH" if p >= prev * 3 else "MEDIUM" if p >= prev * 1.5 else "LOW"
                     for p in p_sc],
            "realized_event": np.where(in_win[idx], 1.0,
                                       np.where(full_hindsight[idx], 0.0, np.nan)),
            "contributors": contrib,
        })
        # reliability band from training decile
        out["conf_decile"] = np.clip(np.digitize(p_sc, bins[1:-1]), 0, 9)
        out["conf_empirical_rate"] = [bin_rate[d] for d in out["conf_decile"]]
        out["train_prevalence"] = prev

        path = OUTPUT / f"wheel_attribution_{target}.parquet"
        out.to_parquet(path, index=False)
        realized_known = out["realized_event"].notna().sum()
        meta["targets"][target] = {
            "n_train": int(tr_mask.sum()), "n_scored": int(n),
            "train_events": int(ytr.sum()), "train_prevalence": prev,
            "realized_known_scored": int(realized_known),
            "realized_events_scored": int(out["realized_event"].sum()),
            "risk_counts": out["risk"].value_counts().to_dict(),
            "out_path": str(path.relative_to(ROOT)),
        }
        print(f"  {target}: scored {n}, realized known {int(realized_known)}, "
              f"events {int(out['realized_event'].sum())}, "
              f"prev {prev:.4f}, risk {out['risk'].value_counts().to_dict()}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "wheel_attribution.json").write_text(
        json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2, default=str))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
