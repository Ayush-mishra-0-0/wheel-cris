"""Pull & render concrete wheel-level next-state walkthrough examples.

Strict point-in-time: freeze features at T, run the serving degradation models,
compare the no-turn forecast path against what actually happened.

NO-TURN example: actual = next same-segment valid measurement after T.
TURN example:    a confirmed lifecycle turn completes at post_ts in (T, T+180];
                 no-turn forecast at the turn vs actual post-turn restored state,
                 plus the recorded restoration operator (cut_dia, post flange/root).
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from dashboard.backend import backtest, service
from models.phase5.dashboard.backend.features import load_wes, extract_features

ML = r"C:\Users\CRIS\Desktop\ayush\wheel-project\ml"
DAY = np.timedelta64(1, "D")
dims = list(backtest.DIMM)

wes_all = load_wes()
turns = backtest._load_confirmed_turns()
degsvc = service.degradation_models()
meta = service.degradation_meta()


def wes_ws(ws: int) -> pd.DataFrame:
    w = wes_all[wes_all["wheelset_equipment_id"] == ws].sort_values("measurement_timestamp").reset_index(drop=True)
    return w


def find_anchor(ws: int, kind: str, want_gap: int):
    w = wes_ws(ws)
    t_arr = w["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    sg = w["seg_id"].to_numpy(dtype="int64")
    qf = w["quality_flags"].to_numpy()
    tr = turns[turns["wheelset_equipment_id"] == ws]["post_ts"].to_numpy(dtype="datetime64[us]")
    best = None
    best_abs = 1e18
    for p in range(len(w) - 1):
        if qf[p] != "valid":
            continue
        t0 = t_arr[p]
        if t0 > w["measurement_timestamp"].iloc[-1] - np.timedelta64(20, "D"):
            continue
        if kind == "no_turn":
            hi = int(np.searchsorted(t_arr, t0 + np.timedelta64(45, "D"), side="right"))
            nxt = None
            for j in range(p + 1, min(hi, len(w))):
                if sg[j] != sg[p]:
                    break
                if qf[j] == "valid" and np.isfinite(w["mean_wsmDia"].iloc[j]):
                    nxt = j
                    break
            if nxt is None:
                continue
            if int(np.searchsorted(tr, t_arr[nxt], side="right") -
                   np.searchsorted(tr, t0, side="left")) != 0:
                continue
            gap = float((t_arr[nxt] - t0) / DAY)
            if abs(gap - want_gap) < best_abs:
                best_abs = abs(gap - want_gap)
                best = (p, pd.Timestamp(t0), pd.Timestamp(t_arr[nxt]))
        else:
            t_hi = t0 + np.timedelta64(180, "D")
            inds = tr[(tr > t0) & (tr <= t_hi)]
            if len(inds) == 0:
                continue
            tb = float((inds[0] - t0) / DAY)
            if tb >= 15 and abs(tb - want_gap) < best_abs:
                best_abs = abs(tb - want_gap)
                best = (p, pd.Timestamp(t0), pd.Timestamp(inds[0]))
    return best


def interp_at(day: float, pts: list):
    if day <= pts[0][0]:
        return pts[0][1]
    for (n1, v1), (n2, v2) in zip(pts, pts[1:]):
        if day <= n2:
            if n2 == n1:
                return v2
            return v1 + (v2 - v1) * (day - n1) / (n2 - n1)
    return pts[-1][1]


def build_grids(res: dict, fr: dict) -> dict:
    grids = {}
    for dim in dims:
        g = {h: None for h in (30, 90, 180)}
        for r in res["degradation"]:
            if r["dim"] == dim and r["predicted"] is not None:
                g[r["horizon"]] = r["predicted"]
        g["current"] = fr.get(f"mean_{dim}")
        grids[dim] = g
    return grids


def path_mae(w: pd.DataFrame, p: int, grids: dict) -> dict:
    t_arr = w["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    sg = w["seg_id"].to_numpy(dtype="int64")
    qf = w["quality_flags"].to_numpy()
    seg = int(sg[p])
    out = {}
    hi = int(np.searchsorted(t_arr, t_arr[p] + np.timedelta64(45, "D"), side="right"))
    for dim, grid in grids.items():
        obs_t, obs_v = [0.0], [grid["current"]]
        for j in range(p + 1, min(hi, len(w))):
            if sg[j] != seg:
                break
            v = w[f"mean_{dim}"].iloc[j]
            if qf[j] == "valid" and np.isfinite(v):
                obs_t.append(float((t_arr[j] - t_arr[p]) / DAY))
                obs_v.append(float(v))
        t_end = obs_t[-1]
        if t_end <= 0.5 or grid["current"] is None or not np.isfinite(grid["current"]):
            out[dim] = None
            continue
        pts = [(0.0, grid["current"])] + [(h, grid[h]) for h in (30, 90, 180) if grid.get(h) is not None]
        s = 0.0
        n = 0
        for day in np.arange(1.0, t_end + 0.001, 1.0):
            f = interp_at(day, pts)
            a = float(np.interp(day, obs_t, obs_v))
            s += abs(f - a)
            n += 1
        out[dim] = round(s / n, 4) if n else None
    return out


def _feat_list(fr: dict) -> list[str]:
    keep = [k for k in fr if k.startswith(("km_last", "mean_", "rate", "ph5_", "days_",
                                          "distance", "wheel_age", "inspection_count", "n_prior"))]
    return sorted(set(keep))


def run_no_turn(ws: int, anchor_ts: pd.Timestamp, target_ts: pd.Timestamp):
    w = wes_ws(ws)
    t_arr = w["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    sg = w["seg_id"].to_numpy(dtype="int64")
    qf = w["quality_flags"].to_numpy()
    p = int(np.where(t_arr == np.datetime64(pd.Timestamp(anchor_ts), "us"))[0][0])
    nxt = None
    hi = int(np.searchsorted(t_arr, t_arr[p] + np.timedelta64(45, "D"), side="right"))
    for j in range(p + 1, min(hi, len(w))):
        if sg[j] != sg[p]:
            break
        if qf[j] == "valid" and np.isfinite(w["mean_wsmDia"].iloc[j]):
            nxt = j
            break
    if nxt is None:
        return {"error": "no same-segment next measurement"}
    target_day = float((t_arr[nxt] - t_arr[p]) / DAY)
    res = backtest.wheelset_replay(ws, anchor_ts)
    if res.get("error"):
        return {"error": res["error"]}
    fr = extract_features(ws, anchor_ts, w=w)
    grids = build_grids(res, fr)
    pred_at = {}
    for dim in dims:
        g = grids[dim]
        pts = [(0.0, g["current"])] + [(h, g[h]) for h in (30, 90, 180) if g.get(h) is not None]
        pred_at[dim] = round(interp_at(target_day, pts), 4)
    actual = {dim: float(w[f"mean_{dim}"].iloc[nxt]) for dim in dims}
    resid = {dim: round(actual[dim] - pred_at[dim], 4) for dim in dims}
    pm = path_mae(w, p, grids)
    pt = {r["horizon"]: r["probability_raw"] for r in res["turn_probability"]}
    return {"ws": ws, "loco": res.get("loco_number"), "anchor_ts": str(anchor_ts.date()),
            "target_ts": str(pd.Timestamp(w["measurement_timestamp"].iloc[nxt]).date()),
            "target_day": round(target_day, 1), "shed": fr.get("home_shed"),
            "quality_target": str(qf[nxt]),
            "features": _feat_list(fr), "fr_cov": service.feature_coverage(fr, degsvc["num_feats"]),
            "current": {d: grids[d]["current"] for d in dims},
            "forecasts": {d: {h: grids[d][h] for h in (30, 90, 180)} for d in dims},
            "pred_at": pred_at, "actual": {d: round(actual[d], 4) for d in dims},
            "residual": resid, "path_mae": pm, "pturn": pt,
            "model_version": meta.get("model_version"), "train_cutoff": meta.get("train_cutoff"),
            "turn_interval": False}


def run_turn(ws: int, anchor_ts: pd.Timestamp, target_ts: pd.Timestamp):
    w = wes_ws(ws)
    t_arr = w["measurement_timestamp"].to_numpy(dtype="datetime64[us]")
    p = int(np.where(t_arr == np.datetime64(pd.Timestamp(anchor_ts), "us"))[0][0])
    tr = turns[(turns["wheelset_equipment_id"] == ws) & (turns["post_ts"] > anchor_ts) &
               (turns["post_ts"] <= target_ts)].sort_values("post_ts")
    if tr.empty:
        return {"error": "no confirmed turn in interval"}
    trk = tr.iloc[0]
    post_ts = pd.Timestamp(trk["post_ts"])
    res = backtest.wheelset_replay(ws, anchor_ts)
    if res.get("error"):
        return {"error": res["error"]}
    fr = extract_features(ws, anchor_ts, w=w)
    grids = build_grids(res, fr)
    day_turn = (post_ts - anchor_ts).days
    pred_no_turn = {}
    for dim in dims:
        g = grids[dim]
        pts = [(0.0, g["current"])] + [(h, g[h]) for h in (30, 90, 180) if g.get(h) is not None]
        pred_no_turn[dim] = round(interp_at(day_turn, pts), 4)
    post_row = None
    for j in range(p + 1, len(w)):
        if pd.Timestamp(w["measurement_timestamp"].iloc[j]) >= post_ts:
            post_row = j
            break
    actual_post = {dim: (float(w[f"mean_{dim}"].iloc[post_row]) if post_row is not None else np.nan) for dim in dims}
    resid = {dim: round(actual_post[dim] - pred_no_turn[dim], 4) for dim in dims}
    pt = {r["horizon"]: r["probability_raw"] for r in res["turn_probability"]}
    qf_post = str(w["quality_flags"].iloc[post_row]) if post_row is not None else "n/a"
    return {"ws": ws, "loco": res.get("loco_number"), "anchor_ts": str(anchor_ts.date()),
            "turn_ts": str(post_ts.date()), "turn_day": day_turn, "shed": fr.get("home_shed"),
            "quality_post_turn": qf_post,
            "features": _feat_list(fr), "fr_cov": service.feature_coverage(fr, degsvc["num_feats"]),
            "current": {d: grids[d]["current"] for d in dims},
            "pred_no_turn_at_turn": pred_no_turn,
            "actual_post_turn": {d: round(actual_post[d], 4) for d in dims},
            "residual": resid,
            "restore": {"cut_dia": trk.get("cut_dia"), "pre_wsmDia": trk.get("pre_wsmDia"),
                        "post_wsmDia": trk.get("post_wsmDia"), "post_wsmFlange": trk.get("post_wsmFlange"),
                        "post_wsmRoot": trk.get("post_wsmRoot")},
            "pturn": pt, "model_version": meta.get("model_version"),
            "train_cutoff": meta.get("train_cutoff"), "turn_interval": True}


PLAN = [
    (406356, "no_turn", 30),   # HIGH pturn 0.368 LGDE - flagged: re-provision at anchor
    (406320, "no_turn", 30),   # LOW risk BZAE - clean flat / noise-floor example
    (30792,  "no_turn", 40),   # LOW risk GZBE - clean smooth dia decline
    (439629, "no_turn", 40),   # HIGH pturn 0.015 BNDL - clean smooth dia decline
    (406950, "turn", 60),      # HIGH pturn 0.378 LGDE - cut 13 mm
    (406083, "turn", 60),      # LOW risk LGDE - cut 4 mm
]


def main():
    snap = pd.read_parquet(ML + r"\model_datasets\v5\fleet_snapshot.parquet")
    snap = snap.set_index("wheelset_equipment_id")
    out = []
    for ws, kind, want in PLAN:
        a = find_anchor(ws, kind, want)
        if a is None:
            out.append({"ws": ws, "kind": kind, "error": "no anchor found"})
            continue
        p, anchor_ts, target_ts = a
        r = run_no_turn(ws, anchor_ts, target_ts) if kind == "no_turn" else run_turn(ws, anchor_ts, target_ts)
        r["kind"] = kind
        if ws in snap.index:
            s = snap.loc[ws]
            r["shed"] = str(s.get("shed_any")).strip()
            r["risk_bucket"] = str(s.get("limiting_dim") or "wear") if pd.notna(s.get("limiting_dim")) else "wear"
            r["pturn_90d"] = float(s.get("pturn_90d")) if pd.notna(s.get("pturn_90d")) else None
            r["days_to_condemning_dia"] = float(s.get("days_to_condemning_dia")) if pd.notna(s.get("days_to_condemning_dia")) else None
            r["loco"] = str(s.get("loco_number"))
        out.append(r)
        with open(r"C:\Users\CRIS\Desktop\ayush\wheel-project\_walkthrough_pull.json", "w") as f:
            json.dump(out, f, default=str, indent=1)
        print("done", ws, kind, "->", r.get("anchor_ts"), "|", r.get("target_ts") or r.get("turn_ts"))


if __name__ == "__main__":
    main()