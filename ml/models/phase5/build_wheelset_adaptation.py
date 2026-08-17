"""Layer 5 - build the wheelset-adaptation stream (second-stage post-processor).

Materialises, for every measurement row in the degradation substrate, the
point-in-time empirical-Bayes residual bias of the SAME wheelset in the SAME
segment, using only rows strictly BEFORE that measurement:

    bias_shrunk = mean(residual over last <=5 prior same-segment rows)
                  * prior_n / (prior_n + K)          (K = 3)

where residual = actual - (current + model_delta) computed with the SAME
serving degradation heads. Rows with < 2 prior same-segment residuals carry
prior_n < 2 and are NOT adapted (regime: wheel-specific estimate unavailable,
or turn/replacement boundary with no segment history).

Output: model_datasets/v5/wheelset_adaptation.parquet

Columns (per (dim, H) in {root,flange,thread,dia} x {30,90,180}):
    wheelset_equipment_id   int
    measurement_timestamp   datetime64[us]
    seg_index               int          segment of THIS row
    is_boundary             bool         turn_event | replacement at THIS row
    n_<dim>_<H>d            int          # prior same-segment residuals used
    bias_<dim>_<H>d         float        EB-shrunk bias (mm), NaN if prior_n<2
    resid_<dim>_<H>d        float        THIS row's own residual (for next rows)
    eligible_<dim>_<H>d     bool         whether THIS row enters future buffers

Point-in-time guarantee: bias at row i uses only rows j<i with seg[j]==seg[i],
walking each wheelset in time order. This is the exact stream the serving path
reads at an anchor to produce the adapted forecast.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
SERV = ROOT / "models" / "phase5" / "serving" / "degradation"
OUT = ROOT / "model_datasets" / "v5" / "wheelset_adaptation.parquet"

DIMM = ("wsmRoot", "wsmFlange", "wsmThread", "wsmDia")
HORIZONS = (30, 90, 180)
K = 3.0
MAX_PRIOR = 5


def main() -> None:
    d = pd.read_parquet(DATA)
    feats = json.loads((SERV / "features.json").read_text())
    NUM, CAT = feats["num_feats"], feats["cat_feats"]
    enc = joblib.load(SERV / "encoder.joblib")
    cat = d[CAT].astype(str).replace({"nan": "NA", "None": "NA"})
    Xc = enc.transform(cat)

    ws = d["wheelset_equipment_id"].to_numpy()
    ts = pd.to_datetime(d["measurement_timestamp"]).to_numpy()
    seg = d["segment_index"].to_numpy()
    boundary = (d["turn_event"].fillna(0).astype(bool) | d["replacement"].fillna(0).astype(bool)).to_numpy()

    # enforce point-in-time order (per wheelset by time)
    order = np.lexsort((ts, ws))
    inv = np.empty_like(order)
    inv[order] = np.arange(len(d))
    d = d.iloc[order].reset_index(drop=True)
    ws = d["wheelset_equipment_id"].to_numpy()
    ts = pd.to_datetime(d["measurement_timestamp"]).to_numpy()
    seg = d["segment_index"].to_numpy()
    boundary = (d["turn_event"].fillna(0).astype(bool) | d["replacement"].fillna(0).astype(bool)).to_numpy()
    cat = d[CAT].astype(str).replace({"nan": "NA", "None": "NA"})
    Xc = enc.transform(cat)

    out = pd.DataFrame({
        "wheelset_equipment_id": ws,
        "measurement_timestamp": ts,
        "seg_index": seg,
        "is_boundary": boundary,
    })

    for dim in DIMM:
        for H in HORIZONS:
            tag = f"{dim}_{H}d"
            gate = d[f"eligible_{dim}_{H}d"].to_numpy() & d[f"tgt_{dim}_{H}d"].notna().to_numpy()
            m = joblib.load(SERV / f"model_{dim}_{H}d.joblib")
            Xn = d.loc[gate, NUM].to_numpy(float)
            X = np.hstack([Xn, Xc[gate]])
            cur = d[f"mean_{dim}"].to_numpy()
            tgt = d[f"tgt_{dim}_{H}d"].to_numpy()
            resid = np.full(len(d), np.nan)
            resid[gate] = tgt[gate] - (cur[gate] + m.predict(X))

            buf = {}  # ws -> list[(ts, seg, resid)]
            n_out = np.zeros(len(d), dtype=int)
            bias_out = np.full(len(d), np.nan)
            for i in range(len(d)):
                w_ = ws[i]
                if np.isfinite(resid[i]) and gate[i]:
                    lst = buf.setdefault(w_, [])
                    lst.append((ts[i], seg[i], resid[i]))
                else:
                    # still compute bias for this row from prior same-segment rows
                    lst = buf.get(w_, [])
                ss = [r for r in lst if r[1] == seg[i]]
                last = ss[-MAX_PRIOR:]
                vals = [r[2] for r in last if np.isfinite(r[2])]
                n_out[i] = len(vals)
                if len(vals) >= 2:
                    bias_out[i] = float(np.mean(vals)) * (len(vals) / (len(vals) + K))

            out[f"n_{tag}"] = n_out
            out[f"bias_{tag}"] = bias_out
            out[f"resid_{tag}"] = resid
            out[f"eligible_{tag}"] = gate

    out.to_parquet(OUT, index=False)
    n_rows = len(out)
    n_adaptable = int(np.sum(out["n_wsmRoot_90d"] >= 2))
    print(f"wrote {OUT.relative_to(ROOT)}: {n_rows} rows, "
          f"{n_adaptable} ({n_adaptable / n_rows * 100:.1f}%) rows with prior_n>=2 (root 90d)")


if __name__ == "__main__":
    main()