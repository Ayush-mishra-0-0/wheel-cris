"""Phase 5 Layer 0 - attach shed attribution to lifecycle turns (and segments).

Priority:
  1. SLAM shed stay covering the turn's post-turn timestamp (loco in shed).
  2. FOIS trackhistory: most recent station <= post_ts; shed if the station is
     one of the loco's known shed codes (from SLAM), else station-only context.
  3. Fallback: home_shed / defect_zone / defect_division from WES.

Writes extensions:
  model_datasets/v5/lifecycle_turns_shed.parquet   (turns + shed columns)
  model_datasets/v5/lifecycle_segments_shed.parquet
  model_datasets/v5/shed_attribution_on_turns.json (coverage summary)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "model_datasets" / "v5"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
TRACKHIST = ROOT / "distance_recovery" / "data" / "fois_trackhistory_wap7.parquet"


def station_shed_lookup() -> tuple[pd.DataFrame, set]:
    """FOIS station codes equal to SLAM shed codes form the shed-station set.

    The FOIS trackhistory source is an external data dependency (gitignored under
    distance_recovery/data/). If it is absent the function degrades to an empty
    lookup; shed attribution then falls back to SLAM stays + WES home_shed only.
    """
    if not TRACKHIST.exists():
        print(f"WARN: {TRACKHIST.name} not found - FOIS station attribution skipped "
              "(SLAM + WES fallback only)")
        return pd.DataFrame(columns=["lom_number", "Station", "t"]), set()
    th = pd.read_parquet(TRACKHIST, columns=["LocoNumber", "Station", "LastLocationTime"])
    th["LocoNumber"] = th["LocoNumber"].astype(str).str.strip()
    th["Station"] = th["Station"].astype(str).str.strip()
    th["t"] = pd.to_datetime(th["LastLocationTime"])
    th = th[["LocoNumber", "Station", "t"]].rename(columns={"LocoNumber": "lom_number"})
    return th, set(th["Station"].dropna().unique())


def lom_number_map() -> dict:
    wes = pd.read_parquet(WES, columns=["locomotive_id", "LomNumber"])
    m = wes.dropna(subset=["LomNumber"]).drop_duplicates("locomotive_id")[
        ["locomotive_id", "LomNumber"]]
    m["LomNumber"] = m["LomNumber"].astype(str).str.strip()
    return dict(zip(m["locomotive_id"], m["LomNumber"]))


def shed_station_map(slam: pd.DataFrame) -> dict:
    """loco_number -> set of known shed codes (from its SLAM stays)."""
    return slam.groupby("loco_number")["shed"].apply(set).to_dict()


def main() -> None:
    turns = pd.read_parquet(V5 / "lifecycle_turns.parquet")
    seg = pd.read_parquet(V5 / "lifecycle_segments.parquet")
    slam = pd.read_parquet(V5 / "loco_shed_stays.parquet")
    wes = pd.read_parquet(WES, columns=["locomotive_id", "home_shed", "defect_zone", "defect_division"])

    loco2lom = lom_number_map()
    shed_of_loco = shed_station_map(slam)

    th, shed_stations = station_shed_lookup()
    th = th.sort_values(["lom_number", "t"])
    th_asof = th.drop_duplicates("lom_number", keep="last")

    def attach(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        ts = df["post_ts"] if "post_ts" in df.columns else df["segment_end_ts"]
        out = df.copy()
        out["post_ts"] = ts
        out["lom_number"] = out["locomotive_id"].map(loco2lom)
        n = len(out)
        shed_slam = np.full(n, None, dtype=object)
        shed_fois = np.full(n, None, dtype=object)
        stn = np.full(n, None, dtype=object)
        for i, r in out.iterrows():
            lom = r["lom_number"]
            tt = r["post_ts"]
            if pd.isna(lom):
                continue
            stays = slam[(slam["loco_number"] == lom) & (slam["start"] <= tt) & (slam["end"] >= tt)]
            if not stays.empty:
                shed_slam[i] = stays.sort_values("start").iloc[-1]["shed"]
        # FOIS: most recent station at/before post_ts (per loco); skip if source absent
        stn_map: dict = {}
        if len(th):
            tgt = out.reset_index(drop=False)[["index", "lom_number", "post_ts"]].rename(columns={"post_ts": "t"})
            tgt = tgt.dropna(subset=["lom_number"]).sort_values("t")
            merged = pd.merge_asof(
                tgt, th.sort_values("t"), on="t", by="lom_number", direction="backward")
            stn_map = dict(zip(merged["index"], merged["Station"]))
        # map stations equal to a shed code
        for i, s in stn_map.items():
            stn[i] = s
            if s in shed_stations:
                shed_fois[i] = s
        out["shed_slam"] = shed_slam
        out["station_fois"] = stn
        out["shed_fois"] = shed_fois
        out["shed_any"] = out["shed_slam"]
        out["shed_any"] = out["shed_any"].fillna(pd.Series(shed_fois, index=out.index))
        ws = wes.set_index("locomotive_id")
        out["home_shed"] = out["locomotive_id"].map(ws["home_shed"].to_dict())
        out["defect_zone"] = out["locomotive_id"].map(ws["defect_zone"].to_dict())
        out["shed_any"] = out["shed_any"].fillna(out["home_shed"])
        cov = {
            "n": int(n),
            "shed_slam": round(float(out["shed_slam"].notna().mean()), 3),
            "station_fois": round(float(out["station_fois"].notna().mean()), 3),
            "shed_fois": round(float(out["shed_fois"].notna().mean()), 3),
            "shed_any_or_home": round(float(out["shed_any"].notna().mean()), 3),
            "defect_zone": round(float(out["defect_zone"].notna().mean()), 3),
        }
        return out, cov

    turns_out, tcov = attach(turns)
    seg_out, scov = attach(seg)
    turns_out.drop(columns=["post_ts"], errors="ignore").to_parquet(V5 / "lifecycle_turns_shed.parquet", index=False)
    seg_out.drop(columns=["post_ts"], errors="ignore").to_parquet(V5 / "lifecycle_segments_shed.parquet", index=False)
    rep = {"turns": tcov, "segments": scov,
           "n_slam_locos": int(slam["loco_number"].nunique())}
    (V5 / "shed_attribution_on_turns.json").write_text(
        json.dumps(rep, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(rep, indent=2, default=str))
    print(V5.relative_to(ROOT))


if __name__ == "__main__":
    main()