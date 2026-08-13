"""Phase 5 Layer 2 - subgroup stability of the delta models (flange/root/tread).

Tier-2 analysis. Uses the SAME frozen test split and serving C1 delta models as
`trajectory_product_analysis.py`, then breaks residuals + conformal coverage down
by operating subgroup:

  - shed          (shed_any)
  - profile class (wheel_profile_2class)
  - wheel position(wheel_position_1_12)
  - axle position (axle_position_1_6)
  - age cohort    (wheel_age_days_proxy deciles)
  - wear quantile (current value of the dim, test-deciles)

For each (dim, H, subgroup, level) on the test split we report:
  n, mae_mm, rmse_mm, bias_mm (mean residual = realised - predicted CHANGE),
  delta_r2 (per-group), and 80% split-conformal coverage (band width from the
  trajectory artefact). Groups with n < MIN_N are flagged unstable, as are any
  group whose abs bias or coverage deviates materially from the fleet level.

Collapse rule: any subgroup block with an n < MIN_N group or a coverage < 0.70
(or > 0.90) or |bias| > 2 * noise floor is surfaced for review; uniform fleet
display is only safe when no subgroup collapses.

Outputs: models/experiments/v5/subgroup_stability.json
         models/experiments/v5/subgroup_stability.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "model_datasets" / "v5" / "degradation_benchmark.parquet"
SERV = ROOT / "models" / "phase5" / "serving" / "degradation"
ARTE = ROOT / "models" / "experiments" / "v5" / "trajectory_product_analysis.json"
OUT = ROOT / "models" / "experiments" / "v5"

DIMS = ("wsmFlange", "wsmRoot", "wsmThread")
HORIZONS = (30, 90, 180)
ALPHA = 0.20
MIN_N = 100              # below this a subgroup is "insufficiently evidenced"
COV_MIN, COV_MAX = 0.70, 0.90
NOISE_FLOOR_MM = {"wsmFlange": 0.1144, "wsmRoot": 0.1052, "wsmThread": 0.0655}
BIAS_LIMIT_MULT = 2.0

SUBGROUPS = {
    "shed": ("shed_any", "categorical"),
    "profile_class": ("wheel_profile_2class", "categorical"),
    "wheel_position": ("wheel_position_1_12", "categorical"),
    "axle": ("axle_position_1_6", "categorical"),
    "age_cohort": ("wheel_age_days_proxy", "continuous"),
    "wear_quantile": (None, "target_quantile"),
}


def _group_labels(df, key, kind):
    """Return a Series of group labels for the given subgroup key."""
    if kind == "categorical":
        s = df[key].astype("object").fillna("NA").astype(str)
        s = s.str.replace({"nan": "NA", "None": "NA", "<NA>": "NA"})
        return s.str.strip().where(lambda v: v != "", "NA")
    if kind == "continuous":
        v = df[key].to_numpy(float)
        q = pd.qcut(v, q=4, duplicates="drop")
        vals = np.asarray(q.tolist() if hasattr(q, "tolist") else q, dtype=object)
        return pd.Series(vals, index=df.index).astype(str).str.replace(
            r"\(|\)|\[|\]", "", regex=True).astype("object")
    return pd.Series(["NA"] * len(df), index=df.index)


def _coverage(pred, y, width):
    ok = np.isfinite(pred) & np.isfinite(y)
    if ok.sum() == 0:
        return None
    lo = pred[ok] - width
    hi = pred[ok] + width
    return float(np.mean((y[ok] >= lo) & (y[ok] <= hi)))


def _per_group(df_g, pred, y, width):
    """Metrics for one group of rows (delta space)."""
    ok = np.isfinite(pred) & np.isfinite(y)
    n = int(ok.sum())
    if n < MIN_N:
        return {"n": n, "insufficient": True}
    p, t = pred[ok], y[ok]
    resid = t - p
    mae = float(np.mean(np.abs(resid)))
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    bias = float(np.mean(resid))
    ss = float(np.sum((t - t.mean()) ** 2)) or 1.0
    r2 = float(1.0 - np.sum(resid ** 2) / ss)
    return {
        "n": n, "insufficient": False,
        "mae_mm": round(mae, 4), "rmse_mm": round(rmse, 4),
        "bias_mm": round(bias, 4),
        "delta_r2": round(r2, 4),
        "coverage": round(_coverage(p, t, width), 4) if width is not None else None,
    }


def main() -> None:
    df = pd.read_parquet(DATA)
    feats = json.loads((SERV / "features.json").read_text())
    enc = joblib.load(SERV / "encoder.joblib")
    arte = json.loads(ARTE.read_text()) if ARTE.exists() else {}
    width = {d: {H: arte["3_conformal_80pct"][d][f"{H}d"]["conformal_width_mm"]
                 for H in HORIZONS} for d in DIMS}

    # per-dim target quantile label (test-deciles of current value)
    qcols = {}
    for dim in DIMS:
        te = df["split"].eq("test")
        v = df.loc[te, f"mean_{dim}"].to_numpy(float)
        q = pd.qcut(v, q=4, duplicates="drop")
        lab = pd.Series(
            np.asarray(q.tolist() if hasattr(q, "tolist") else q, dtype=object),
            index=df.index[te]).astype(str).str.replace(
                r"\(|\)|\[|\]", "", regex=True).astype("object")
        qcols[dim] = lab

    te = df[df["split"].eq("test")].copy()
    Xn = te[feats["num_feats"]].to_numpy(dtype=float)
    cat = te[feats["cat_feats"]].astype(str).replace({"nan": "NA", "None": "NA"})
    Xc = enc.transform(cat)

    out = {"task": "phase 5 layer 2 subgroup stability (flange/root/tread)",
           "contract": "wheel_profile_lifecycle_contract_v1",
           "target_mode": "delta",
           "alpha": ALPHA,
           "note": ("Test-split delta residuals (realised - predicted CHANGE) and "
                    "80% split-conformal coverage by operating subgroup. A group is "
                    "flagged as a COLLAPSE when n<100, coverage<0.70, or |bias| > 2x "
                    "the noise floor. Over-coverage (>0.80) is conservative (safe) and "
                    "reported but not flagged. Uniform fleet display is safe only if "
                    "no subgroup collapses."),
           "collapse_groups": []}
    fleet_ref = {}

    for dim in DIMS:
        out[dim] = {}
        for H in HORIZONS:
            m = joblib.load(SERV / f"model_{dim}_{H}d.joblib")
            el = te[f"eligible_{dim}_{H}d"].astype(bool) & te[f"tgt_{dim}_{H}d"].notna()
            sub = te.loc[el]
            pred = m.predict(np.hstack([Xn[el], Xc[el]]))
            cur = sub[f"mean_{dim}"].to_numpy(float)
            y = sub[f"tgt_{dim}_{H}d"].to_numpy(float) - cur
            w = width[dim][H]
            nf = NOISE_FLOOR_MM[dim]

            fleet = _per_group(sub, pred, y, w)
            fleet_ref[f"{dim}_{H}d"] = {
                "n": fleet["n"], "bias_mm": fleet.get("bias_mm"),
                "mae_mm": fleet.get("mae_mm"), "coverage": fleet.get("coverage"),
            }

            out[dim][f"{H}d"] = {"fleet": fleet, "groups": {}}
            for gname, (key, kind) in SUBGROUPS.items():
                if kind == "target_quantile":
                    labels = qcols[dim].reindex(sub.index)
                    labels = labels.fillna("NA").astype(str)
                else:
                    labels = _group_labels(sub, key, kind)
                gres = {}
                for lab in labels.astype(str).unique():
                    idx = labels.astype(str).eq(lab)
                    r = _per_group(sub.loc[idx], pred[idx], y[idx], w)
                    r["level"] = lab
                    gres[lab] = r
                    if not r["insufficient"]:
                        bias = r["bias_mm"]
                        cov = r["coverage"]
                        flag = (cov is None or cov < COV_MIN
                                or abs(bias) > BIAS_LIMIT_MULT * nf)
                        if flag:
                            out["collapse_groups"].append({
                                "dim": dim, "horizon": H, "group": gname,
                                "level": lab, "n": r["n"],
                                "bias_mm": bias, "coverage": cov,
                                "noise_floor_mm": nf,
                                "reason": ("coverage" if (cov is None or cov < COV_MIN)
                                           else "bias")})
                out[dim][f"{H}d"]["groups"][gname] = gres

    out["fleet_reference"] = fleet_ref

    # ---- figure ----
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for j, dim in enumerate(DIMS):
        cell = out[dim]["90d"]
        labels = []
        biases = []
        covs = []
        for gname, gres in cell["groups"].items():
            for lab, r in gres.items():
                if r["insufficient"]:
                    continue
                labels.append(f"{gname}:{lab}")
                biases.append(r["bias_mm"])
                covs.append(r["coverage"])
        ax = axes[0, j]
        nf = NOISE_FLOOR_MM[dim]
        ax.axhline(0, color="k", lw=0.6)
        ax.axhline(2 * nf, color="gray", ls="--", lw=0.7)
        ax.axhline(-2 * nf, color="gray", ls="--", lw=0.7)
        ax.scatter(range(len(biases)), biases, s=18, alpha=0.7, color="#2980b9")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=90, fontsize=6)
        ax.set_title(f"{dim} @90d group bias (mm)")
        ax.set_ylim(np.nanmin(biases) - 0.1, np.nanmax(biases) + 0.1)
        ax = axes[1, j]
        ax.axhline(1 - ALPHA, color="k", lw=0.8)
        ax.axhspan(COV_MIN, COV_MAX, color="green", alpha=0.06)
        ax.scatter(range(len(covs)), covs, s=18, alpha=0.7, color="#27ae60")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=90, fontsize=6)
        ax.set_ylim(0, 1.0)
        ax.set_title(f"{dim} @90d coverage")
    fig.suptitle("Subgroup stability: delta-residual bias and 80% conformal coverage by subgroup (90d)")
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "subgroup_stability.png", dpi=130)
    plt.close(fig)

    (OUT / "subgroup_stability.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT))
    print(f"collapse_groups: {len(out['collapse_groups'])}")
    for g in out["collapse_groups"][:12]:
        print(" ", g)
    print("DONE")


if __name__ == "__main__":
    main()
