"""Phase 4 - never-seen-loco holdout (transferability stress, plan section 8).

Secondary stress test (evaluation hierarchy: 2 after the rolling simulation):
~20% of locomotives are withheld from training ENTIRELY (all rows, all time).
The candidate and baselines are fit only on rows whose locomotive was seen in
training, then scored on the held-out locomotives' rows. Proves whether we learn
general wheel behaviour rather than this loco's history. Failure to generalize
is reported as a stress, not hidden.

Design:
  * Hold out by locomotive_id (per-row mapping from WES via measurement_record_id,
    so wheelsets that migrate across locos are assigned to their actual loco).
  * Labels/eligibility identical to the rolling benchmark: event strictly inside
    (t, t+H]; static (full-hindsight) eligibility.
  * Models: B0 prevalence, B1 regularized logistic, B2 margin-only, C1 XGBoost.
  * Metrics: PR-AUC, ROC-AUC, Brier, ECE, capture@5/10%, lift@5/10%.

Output: models/experiments/v4/loco_holdout.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_rolling_risk_benchmark import (  # noqa: E402
    NUM_FEATS, CAT_FEATS, LIMIT_ROOT, HORIZONS, SEED, ece, pr_auc, roc_auc,
    capture_at, lift_at, build_matrix,
)

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "model_datasets" / "v4" / "risk_benchmark.parquet"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v4"
HOLDOUT_FRAC = 0.20


def main() -> None:
    df = pd.read_parquet(V4)
    wes = pd.read_parquet(WES, columns=[
        "wheelset_equipment_id", "measurement_record_id", "measurement_timestamp",
        "turning_record_at_measurement", "wsmRoot1", "wsmRoot2",
        "wsmRoot1_quality", "wsmRoot2_quality", "locomotive_id"])

    # per-row loco mapping
    loco_map = wes.drop_duplicates("measurement_record_id")[
        ["measurement_record_id", "locomotive_id"]]
    df = df.merge(loco_map, on="measurement_record_id", how="left")
    if df["locomotive_id"].isna().any():
        raise RuntimeError("loco mapping incomplete; aborting")

    # ---- point-in-time event structures (reuse rolling-benchmark logic) ----
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

    # ---- holdout split by locomotive_id ----
    rng = np.random.default_rng(SEED)
    locos = np.sort(df["locomotive_id"].unique())
    n_hold = int(len(locos) * HOLDOUT_FRAC)
    holdout_ids = set(rng.choice(locos, size=n_hold, replace=False))
    ho = df["locomotive_id"].isin(holdout_ids).to_numpy()

    Xall = build_matrix(df)
    all_rows = pd.DataFrame({
        "t": t0, "first_root": first_root, "first_turn": first_turn,
        "obs_end_full": obs_end_full,
    })

    out = {
        "task": "phase 4 never-seen-loco holdout (transferability stress)",
        "status": "stress test (evaluation hierarchy 2); ~20% of locomotives fully held out",
        "n_loco_total": int(len(locos)), "n_loco_holdout": int(n_hold),
        "n_holdout_rows": int(ho.sum()), "n_train_rows": int((~ho).sum()),
        "holdout_fraction": HOLDOUT_FRAC,
        "split_unit": "locomotive_id (per-row via measurement_record_id; wheelsets may migrate)",
        "targets": {},
    }

    for target, ev_time, ev_name in (("root", "first_root", "root_within"),
                                     ("turn", "first_turn", "turn_within")):
        for H in HORIZONS:
            ev = all_rows[ev_time].to_numpy()
            in_win = (ev != np.datetime64("NaT")) & ((ev - t0) <= np.timedelta64(H, "D"))
            y_true = in_win.astype(float)
            static_elig = ((all_rows["obs_end_full"].to_numpy() - t0) >= np.timedelta64(H, "D")) | in_win
            tr_mask = (~ho) & static_elig
            ev_mask = ho & static_elig
            ntr = int(tr_mask.sum()); nev = int(ev_mask.sum())
            ev_tr = int(y_true[tr_mask].sum()); ev_ev = int(y_true[ev_mask].sum())
            if ntr < 500 or nev < 100 or ev_tr < 20:
                out["targets"].setdefault(target, {})[str(H)] = {"insufficient_data": True,
                                                                 "n_train": ntr, "n_eval": nev}
                continue

            ytr = y_true[tr_mask]; yev = y_true[ev_mask]
            # B0 prevalence (train rate)
            prev = ytr.mean()
            p0 = np.full(nev, prev)
            # B1 logistic
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            Xtr = Xall[tr_mask]; Xev = Xall[ev_mask]
            Xtrf = np.nan_to_num(Xtr, nan=0.0); Xevf = np.nan_to_num(Xev, nan=0.0)
            sc = StandardScaler().fit(Xtrf)
            lr = LogisticRegression(C=0.1, max_iter=1000, random_state=SEED)
            lr.fit(sc.transform(Xtrf), ytr)
            p1 = lr.predict_proba(sc.transform(Xevf))[:, 1]
            # B2 margin-only
            mcol = df["wsmRoot_mean"].to_numpy(dtype=float)
            marg = LIMIT_ROOT - mcol
            mt = marg[tr_mask].reshape(-1, 1); ms = marg[ev_mask].reshape(-1, 1)
            p2 = np.full(nev, np.nan)
            okm = np.isfinite(mt).ravel()
            if okm.sum() >= 50 and ytr[okm].sum() > 0 and (okm.sum() - ytr[okm].sum()) > 0:
                lrm = LogisticRegression(C=1.0, max_iter=1000)
                lrm.fit(mt[okm], ytr[okm])
                p2 = lrm.predict_proba(np.nan_to_num(ms, nan=0.0))[:, 1]
            # C1 XGBoost
            from xgboost import XGBClassifier
            xgb = XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1,
                                subsample=0.9, colsample_bytree=0.9, random_state=SEED,
                                n_jobs=-1, tree_method="hist", eval_metric="logloss")
            xgb.fit(sc.transform(Xtrf), ytr)
            p3 = xgb.predict_proba(sc.transform(Xevf))[:, 1]

            def cell(p):
                return {"pr_auc": pr_auc(p, yev), "roc_auc": roc_auc(p, yev),
                        "brier": round(float(np.nanmean((p - yev) ** 2)), 5),
                        "ece": ece(p, yev),
                        "capture5": capture_at(p, yev, 0.05),
                        "capture10": capture_at(p, yev, 0.10),
                        "lift5": lift_at(p, yev, 0.05),
                        "lift10": lift_at(p, yev, 0.10)}

            out["targets"].setdefault(target, {})[str(H)] = {
                "n_train": int(ntr), "n_eval": int(nev),
                "train_events": int(ev_tr), "eval_events": int(ev_ev),
                "prevalence_train": round(float(prev), 5),
                "prevalence_eval": round(float(yev.mean()), 5),
                "B0": cell(p0), "B1_logistic": cell(p1),
                "B2_margin": cell(p2), "C1_xgb": cell(p3),
            }
            print(f"  {target:5s} H={H:3d} n_train={ntr} n_eval={nev} eval_events={ev_ev} done")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "loco_holdout.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
