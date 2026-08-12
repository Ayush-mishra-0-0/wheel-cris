"""Phase 5 Layer 1.5 - Turning-behaviour & degradation event study (v2).

Two concepts are kept separate throughout:
  1. Wheel DEGRADATION/STATE (engineering prediction objective): flange/root/
     tread wear and diameter as they grow between turning events.
  2. TURNING BEHAVIOUR (historical shed policy): the shed's actual decision —
     "at what pre-turn state did it cut, and how much diameter was removed".
     We do NOT treat reaching a limit as the turning rule; the limit register is
     shown only as reference and limiting dimension.

Plots:
  P1 pre-turn flange/root/tread (x/y pairs) vs actual cut (colour) - 3 panels
  P2 actual cut vs RDSO empirical cut (D = 2.22*root + 1.3*flange + 0.3*tread)
     with y=x and tolerance (+2.5/-0.6); residual breakdowns
  P3 shed cut policy (median +/- IQR by shed, min-event filter)
  P4 wheelset sawtooth trajectories (wear reset down at turn; dia is consequence)
  P5 wheel life estimate from provision + wear/dia history (turn != end of life)

Cohorts (senior rule: latest 2 years is the PRIMARY training cohort):
  CFT  full-history
  C2Y  last 2 years (>= 2024-08-12)      <- primary production cohort
  COLD older-history (<= 2023-12-31)     <- policy/cohort shift study

Output: models/phase5/report/turnpolicy_*.png, event_study_turnpolicy.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "model_datasets" / "v5"
WES = ROOT / "model_datasets" / "v3" / "wheel_engineering_state_v1.0.parquet"
OUT = ROOT / "models" / "phase5" / "report"

C2Y_CUTOFF = pd.Timestamp("2024-08-12")   # latest 2 years (as of 2026-08-12)
COLD_CUTOFF = pd.Timestamp("2023-12-31")  # strict older-history

LIMITS = {"flange": 3.0, "root": 6.0, "tread": 6.5}
DIA_FLOOR = 1016.0
RDSO = {"root": 2.22, "flange": 1.3, "tread": 0.3}
TOL_LO, TOL_HI = -0.6, +2.5

WEAR_PANELS = [("flange", "root"), ("flange", "tread"), ("root", "tread")]
COL = {"flange": "wsmFlange", "root": "wsmRoot", "tread": "wsmThread"}


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    turns = pd.read_parquet(V5 / "lifecycle_turns_shed.parquet")
    seg = pd.read_parquet(V5 / "lifecycle_segments_shed.parquet")
    turns["pre_ts"] = pd.to_datetime(turns["pre_ts"])
    seg["segment_start_ts"] = pd.to_datetime(seg["segment_start_ts"])
    seg["segment_end_ts"] = pd.to_datetime(seg["segment_end_ts"])

    # ---- shed normalization (drop trailing-space variants) ----
    turns["shed"] = turns["shed_any"].astype(str).str.strip()
    seg["shed"] = seg["shed_any"].astype(str).str.strip()
    turns["shed"] = turns["shed"].replace({"nan": np.nan})
    seg["shed"] = seg["shed"].replace({"nan": np.nan})

    # ---- RDSO expected cut & residual (event-by-event) ----
    tr = turns.copy()
    tr["rdso_cut"] = (
        RDSO["root"] * tr["pre_wsmRoot"]
        + RDSO["flange"] * tr["pre_wsmFlange"]
        + RDSO["tread"] * tr["pre_wsmThread"])
    tr["residual"] = tr["cut_dia"] - tr["rdso_cut"]
    tr["in_tolerance"] = (tr["residual"] >= TOL_LO) & (tr["residual"] <= TOL_HI)
    tr["cohort"] = np.select(
        [tr["pre_ts"] >= C2Y_CUTOFF, tr["pre_ts"] <= COLD_CUTOFF],
        ["C2Y_last2y", "COLD_older"],
        default="C_mid")
    norm = np.column_stack([
        tr["pre_wsmFlange"].to_numpy(dtype=float) / LIMITS["flange"],
        tr["pre_wsmRoot"].to_numpy(dtype=float) / LIMITS["root"],
        tr["pre_wsmThread"].to_numpy(dtype=float) / LIMITS["tread"]])
    labels = np.empty(len(tr), dtype=object)
    ok = np.isfinite(norm).all(axis=1)
    labels[~ok] = None
    labels[ok] = np.take(["flange", "root", "tread"], np.nanargmax(norm[ok], axis=1))
    tr["limiting_dim"] = labels
    return tr, seg, turns


def fig(name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    plt.tight_layout()
    plt.savefig(p, dpi=130, bbox_inches="tight")
    plt.close()
    return p


def plot_prestate_vs_cut(tr: pd.DataFrame) -> Path:
    """3 x/y pre-turn wear panels coloured by actual cut."""
    f, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, (dim_x, dim_y) in zip(axes, WEAR_PANELS):
        cx, cy = COL[dim_x], COL[dim_y]
        d = tr.dropna(subset=[f"pre_{cx}", f"pre_{cy}", "cut_dia"])
        sc = ax.scatter(d[f"pre_{cx}"], d[f"pre_{cy}"],
                        c=d["cut_dia"], s=10, alpha=0.7, cmap="viridis")
        ax.set_xlabel(f"pre-turn {dim_x} (mm)")
        ax.set_ylabel(f"pre-turn {dim_y} (mm)")
        ax.set_title(f"{dim_x} vs {dim_y}\n(colour = actual cut, n={len(d):,})")
        plt.colorbar(sc, ax=ax, label="actual cut (mm)")
        ax.axvline(LIMITS[dim_x], color="red", ls=":", lw=1.5)
        ax.axhline(LIMITS[dim_y], color="red", ls=":", lw=1.5)
    f.suptitle("P1. Shed's pre-turn wear state vs diameter actually removed", fontsize=14)
    return fig("turnpolicy_p1_prestate_vs_cut.png")


def plot_rdso(tr: pd.DataFrame) -> Path:
    """P2 actual cut vs RDSO expectation, y=x + tolerance band, residuals."""
    d = tr.dropna(subset=["cut_dia", "rdso_cut"])
    r = tr.dropna(subset=["residual"])
    f, axes = plt.subplots(1, 3, figsize=(18, 5))

    ax = axes[0]
    ax.scatter(d["rdso_cut"], d["cut_dia"], s=8, alpha=0.45, color="#1f77b4")
    lim = [0, max(d["cut_dia"].max(), d["rdso_cut"].max(), 15)]
    ax.plot(lim, lim, "r--", lw=1.5, label="y=x")
    ax.fill_between(lim, [v - 0.6 for v in lim], [v + 2.5 for v in lim],
                    color="grey", alpha=0.2, label="tol +2.5 / -0.6")
    ax.set_xlabel("RDSO expected cut D = 2.22r+1.3f+0.3t (mm)")
    ax.set_ylabel("actual cut (mm)")
    ax.set_title(f"n={len(d):,}   in-tol {(d['in_tolerance'].mean()*100):.1f}%")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(lim); ax.set_ylim(lim)

    ax = axes[1]
    ax.hist(r["residual"], bins=50, color="#ff7f0e", alpha=0.9)
    ax.axvline(0, color="red", lw=1.5)
    ax.axvline(TOL_LO, color="grey", ls=":"); ax.axvline(TOL_HI, color="grey", ls=":")
    ax.set_xlabel("residual = actual - RDSO (mm)")
    ax.set_title(f"residual median={r['residual'].median():.2f}  "
                 f"p10={r['residual'].min():.2f}  (n={len(r):,})")

    ax = axes[2]
    d2 = r.groupby("shed")["residual"].agg(["mean", "count", "median"]).query("count >= 15")
    d2 = d2.sort_values("mean")
    ax.barh(d2.index.astype(str), d2["mean"], color="#2ca02c", alpha=0.8)
    ax.axvline(0, color="red", lw=1.5)
    ax.set_xlabel("mean residual by shed (mm)")
    ax.set_title(f"residual by shed (>=15 events, n={len(d2)} sheds)")
    f.suptitle("P2. Actual cut vs RDSO empirical cut", fontsize=14)
    return fig("turnpolicy_p2_rdso.png")


def plot_shed_policy(tr: pd.DataFrame) -> Path:
    """P3 shed cut policy: median +/- IQR by shed (min-event filter)."""
    d = tr.dropna(subset=["shed", "cut_dia"])
    g = d.groupby("shed")["cut_dia"].agg(["count", "median", lambda z: z.quantile(0.25),
                                          lambda z: z.quantile(0.75)])
    g.columns = ["count", "median", "q25", "q75"]
    g = g[g["count"] >= 20].sort_values("median")
    if g.empty:
        return Path("")
    meds = g["median"].astype(float); lo = (g["median"] - g["q25"]).astype(float)
    hi = (g["q75"] - g["median"]).astype(float)
    f, ax = plt.subplots(figsize=(12, max(4, len(g) * 0.3)))
    y = np.arange(len(g))
    ax.barh(y, meds, xerr=[lo.to_numpy(), hi.to_numpy()], capsize=3,
            color="#5499c7", alpha=0.9)
    ax.set_yticks(y); ax.set_yticklabels(g.index.astype(str))
    ax.axvline(tr["cut_dia"].median(), color="red", ls="--", lw=1.5,
               label=f"overall median {tr['cut_dia'].median():.1f}mm")
    ax.set_xlabel("median actual cut (mm, IQR bars)")
    ax.set_title(f"P3. Shed cut policy varies by shed (n={len(g)} sheds, >=20 turns each)")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    f.set_tight_layout(True)
    return fig("turnpolicy_p3_shed_policy.png")


def plot_sawtooth(turns: pd.DataFrame) -> Path:
    """P4 wheelset sawtooth trajectories: wear resets at turn; dia is consequence."""
    ws_want = turns.groupby("wheelset_equipment_id").size()
    ws_want = ws_want[ws_want >= 3]
    dims = ["wsmRoot", "wsmFlange", "wsmThread"]
    rows = []
    for ws in ws_want.index:
        sub = turns[turns["wheelset_equipment_id"] == ws].sort_values("pre_ts")
        if len(sub) >= 3 and sub[["pre_wsmRoot", "pre_wsmFlange", "pre_wsmThread"]].notna().all().all():
            rows.append(sub)
        if len(rows) >= 2:
            break
    if not rows:
        return Path("")
    f, axes = plt.subplots(len(rows), 3, figsize=(18, 5 * len(rows)))
    if len(rows) == 1:
        axes = axes[None, :]
    for col, ws_sub in enumerate(rows):
        wsid = ws_sub["wheelset_equipment_id"].max()
        ts = ws_sub.sort_values("pre_ts")
        for j, dim in enumerate(dims):
            ax = axes[col, j]
            dimname = "tread" if dim == "wsmThread" else dim.replace("wsm", "").lower()
            all_x = []; all_y = []
            for i, r in ts.iterrows():
                all_x.append(r["pre_ts"]); all_y.append(r[f"pre_{dim}"])
                all_x.append(r["pre_ts"] + pd.Timedelta(days=1)); all_y.append(r[f"post_{dim}"])
            ax.plot(all_x, all_y, "-o", color="#7f3f98", lw=1.6, ms=3.5, alpha=0.9)
            for i, r in ts.iterrows():
                ax.annotate(f"cut{r['cut_dia']:.0f}",
                            (r["pre_ts"] + pd.Timedelta(days=8), r[f"pre_{dim}"]),
                            fontsize=7, color="#c0392b")
            ax.axhline(LIMITS[dimname], color="red", ls=":", lw=1.5, label=f"limit {LIMITS[dimname]:.1f}mm")
            ax.set_title(f"{dim} — wheelset {wsid}")
            ax.set_ylabel(f"{dim} (mm)")
            ax.legend(fontsize=8)
    f.suptitle("P4. Wheel degradation sawtooth (wear resets DOWN at turning; diameter is the cost)",
               fontsize=14)
    f.set_tight_layout(True)
    return fig("turnpolicy_p4_sawtooth.png")


def plot_wheel_life(turns: pd.DataFrame) -> Path:
    """P5 wheel-life estimate from provision date + observed wear/dia history.

    Life = years-from-provision of the wheelset's measurement stream. A turning
    event is NOT end-of-life: it consumes diameter but resets wear, so the wheel
    keeps working until dia approaches the floor.
    """
    wes = pd.read_parquet(WES, columns=[
        "wheelset_equipment_id", "measurement_timestamp", "wsmProvDate",
        "wheel_age_date_source", "wsmDia1"])
    wes["measurement_timestamp"] = pd.to_datetime(wes["measurement_timestamp"])
    prov = pd.to_datetime(wes["wsmProvDate"], errors="coerce")
    prov_pairs = wes[["wheelset_equipment_id"]].copy()
    prov_pairs["prov_date"] = prov
    prov_map = prov_pairs.dropna(subset=["prov_date"]).groupby("wheelset_equipment_id")[
        "prov_date"].min()
    wes["prov_date"] = wes["wheelset_equipment_id"].map(prov_map)
    wes["age_years"] = (wes["measurement_timestamp"] - wes["prov_date"]).dt.total_seconds() / (
        365.25 * 86400)
    wes = wes[(wes["wsmDia1"] > 0) & (wes["age_years"].between(0, 25))]
    wes["cohort"] = np.select(
        [wes["measurement_timestamp"] >= C2Y_CUTOFF,
         wes["measurement_timestamp"] <= COLD_CUTOFF],
        ["C2Y_last2y", "COLD_older"], default="C_mid")
    f, axes = plt.subplots(1, 3, figsize=(18, 5))
    ax = axes[0]
    for cohort, c in [("COLD_older", "#e74c3c"), ("C_mid", "#f1c40f"), ("C2Y_last2y", "#2e86c1")]:
        sub = wes[wes["cohort"] == cohort]
        if len(sub):
            ax.scatter(sub["age_years"], sub["wsmDia1"], s=3, alpha=0.15, color=c,
                       label=f"{cohort} (n={len(sub):,})")
    ax.axhline(DIA_FLOOR, color="red", lw=1.5, label=f"floor {DIA_FLOOR}mm")
    ax.axhline(1020, color="grey", ls=":", lw=1.5, label="safe 1020mm")
    ax.set_xlabel("wheelset age from provisioning (yr)")
    ax.set_ylabel("diameter (mm)")
    ax.set_xlim(0, 14); ax.set_ylim(1000, 1100)
    ax.set_title("P5a. Diameter vs age from provisioning")
    ax.legend(fontsize=8)

    ax = axes[1]
    last = wes.sort_values("measurement_timestamp").groupby("wheelset_equipment_id").tail(1)
    last = last[last["cohort"].isin(["COLD_older", "C2Y_last2y"])]
    ax.hist([last.loc[last["cohort"] == "COLD_older", "age_years"],
             last.loc[last["cohort"] == "C2Y_last2y", "age_years"]],
            bins=40, alpha=0.6, label=["older cohort", "last-2y cohort"], color=["#e74c3c", "#2e86c1"])
    ax.set_xlabel("age at last observation (yr)"); ax.set_xlim(0, 14)
    ax.set_title("P5b. Wheelset age at last seen")
    ax.legend(fontsize=8)

    ax = axes[2]
    sub = last.dropna(subset=["age_years"]).copy()
    sub["dia_rate"] = (1096.0 - sub["wsmDia1"]) / sub["age_years"].clip(lower=0.1)
    sub["years_to_floor"] = np.where(sub["dia_rate"] > 0,
                                     (sub["wsmDia1"] - DIA_FLOOR) / sub["dia_rate"],
                                     np.nan)
    sub = sub.replace([np.inf, -np.inf], np.nan).dropna(subset=["years_to_floor"])
    sub = sub[sub["years_to_floor"].between(0, 20)]
    for cohort, c in [("COLD_older", "#e74c3c"), ("C2Y_last2y", "#2e86c1")]:
        s = sub[sub["cohort"] == cohort]
        if len(s):
            ax.hist(s["years_to_floor"], bins=40, alpha=0.6, color=c,
                    label=f"{cohort} med={np.median(s['years_to_floor']):.1f}yr")
    ax.set_xlabel("estimated years until dia floor (linear on observed rate)")
    ax.set_xlim(0, 20)
    ax.set_title("P5c. Estimated remaining wheel life to dia floor")
    ax.legend(fontsize=8)

    f.suptitle("P5. Wheel life — turning is NOT end-of-life; diameter cost is the life driver",
               fontsize=14)
    f.set_tight_layout(True)
    return fig("turnpolicy_p5_wheel_life.png")


def main() -> None:
    tr, seg, turns = load()
    paths = {
        "p1_prestate_vs_cut": str(plot_prestate_vs_cut(tr)),
        "p2_rdso": str(plot_rdso(tr)),
        "p3_shed_policy": str(plot_shed_policy(tr)),
        "p4_sawtooth": str(plot_sawtooth(turns)),
        "p5_wheel_life": str(plot_wheel_life(turns)),
    }
    r = tr.dropna(subset=["residual"])
    summary = {
        "n_turns": int(len(tr)),
        "n_turns_rdso": int(len(r)),
        "primary_cohort": f"last-2y >= {str(C2Y_CUTOFF.date())}",
        "cohort_counts": tr["cohort"].value_counts().to_dict(),
        "cut": {
            "median": round(float(tr["cut_dia"].median()), 2),
            "p25": round(float(tr["cut_dia"].quantile(0.25)), 2),
            "p75": round(float(tr["cut_dia"].quantile(0.75)), 2),
        },
        "pre_turn_state": {
            dim: {"median": round(float(tr[f"pre_{COL[dim]}"].median()), 2),
                  "p90": round(float(tr[f"pre_{COL[dim]}"].quantile(0.90)), 2),
                  "pct_over_limit": round(float((tr[f"pre_{COL[dim]}"] > LIMITS[dim]).mean() * 100), 2)}
            for dim in LIMITS
        },
        "limiting_dimension_at_turn": tr["limiting_dim"].value_counts().to_dict(),
        "rdso": {
            "median_residual": round(float(r["residual"].median()), 2),
            "mean_residual": round(float(r["residual"].mean()), 2),
            "pct_in_tolerance": round(float(r["in_tolerance"].mean() * 100), 2),
            "residual_by_cohort": {c: round(float(r.loc[r["cohort"] == c, "residual"].mean()), 2)
                                   for c in ["C2Y_last2y", "COLD_older", "C_mid"]},
        },
        "shed_policy": {
            "n_sheds_stats": int(tr.dropna(subset=["shed"]).groupby("shed")["cut_dia"].count().ge(20).sum()),
        },
        "cohort_comparison": {
            c: {
                "n_turns": int((tr["cohort"] == c).sum()),
                "median_cut": round(float(tr.loc[tr["cohort"] == c, "cut_dia"].median()), 2),
                "median_pre_flange": round(float(tr.loc[tr["cohort"] == c, "pre_wsmFlange"].median()), 2),
                "median_pre_root": round(float(tr.loc[tr["cohort"] == c, "pre_wsmRoot"].median()), 2),
                "median_pre_tread": round(float(tr.loc[tr["cohort"] == c, "pre_wsmThread"].median()), 2),
                "median_rdso_residual": round(float(r.loc[r["cohort"] == c, "residual"].median()), 2),
                "pct_in_tolerance": round(float(r.loc[r["cohort"] == c, "in_tolerance"].mean() * 100), 2),
                "limiting_dim": tr.loc[tr["cohort"] == c, "limiting_dim"].value_counts().to_dict(),
            }
            for c in ["C2Y_last2y", "COLD_older", "C_mid"]
        },
        "figures": paths,
    }
    (OUT / "event_study_turnpolicy.json").write_text(json.dumps(summary, indent=2, default=str) + "\n",
                                                     encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()