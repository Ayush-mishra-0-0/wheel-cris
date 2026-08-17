"""Render the pulled walkthrough examples into NEXT_STATE_WALKTHROUGH.md."""
from __future__ import annotations

import json

import pandas as pd

from dashboard.backend import service

D = json.load(open(r"C:\Users\CRIS\Desktop\ayush\wheel-project\_walkthrough_pull.json"))
NOISE = service.trajectory_artefact()["2_noise_floor"]
CONF = service.trajectory_artefact()["3_conformal_80pct"]
DIM_LBL = {"wsmDia": "d", "wsmFlange": "f", "wsmRoot": "r", "wsmThread": "t"}
DIM_ORDER = ["wsmDia", "wsmFlange", "wsmRoot", "wsmThread"]


def risk(r):
    p = r.get("pturn_90d") or 0
    dc = r.get("days_to_condemning_dia")
    if p >= 0.01 or (dc is not None and dc <= 180):
        return "HIGH"
    return "LOW"


def fmt(v, nd=2):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{float(v):.{nd}f}"


def ptfmt(v):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{float(v) * 100:.1f}%"


def nearest_width(dim, day):
    h = 30 if day <= 30 else 90 if day <= 90 else 180
    c = CONF[dim].get(f"{h}d", {}).get("conformal_width_mm")
    return h, c


def block(r) -> str:
    kind = r["kind"]
    risk_lbl = risk(r) + ("-RISK" if risk(r) == "HIGH" else "-risk")
    loco, ws, shed = r["loco"], r["ws"], r["shed"]
    lines = []
    if kind == "no_turn":
        target_day = r["target_day"]
        lines.append(f"### {ws} — LOCO {loco} / shed {shed}  ·  {risk_lbl}  ·  NO-TURN interval")
        lines.append("")
        lines.append(f"Prediction time T = **{r['anchor_ts']}**  (last valid WSM, quality = OBSERVED_VALID)")
        feats = ", ".join(r["features"][:6]) + ", …"
        lines.append(f"Features used: *[{feats}]*  (feature coverage {fmt(r['fr_cov'] * 100, 0)}%)")
        lines.append("")
        lines.append(f"No-turn forecast at T+{fmt(target_day, 0)} d (piecewise-linear 30/90/180 path):")
        for d in DIM_ORDER:
            lines.append(f"  {DIM_LBL[d]}̂ = {fmt(r['pred_at'][d])} mm")
        lines.append(f"")
        lines.append(f"Actual next measurement ({r['target_ts']}):")
        for d in DIM_ORDER:
            lines.append(f"  {DIM_LBL[d]} = {fmt(r['actual'][d])} mm")
        lines.append(f"  (quality = {r['quality_target'].replace('valid', 'OBSERVED_VALID')}, no turn recorded)")
        lines.append("")
        lines.append("Residuals (actual − forecast):")
        resid = []
        for d in DIM_ORDER:
            rr = r["residual"][d]
            sigma = NOISE[d]["central_sigma_mm"]
            resid.append(f"Δ{DIM_LBL[d]} = {rr:+.2f} mm")
        lines.append("  " + ", ".join(resid))
        pm = r["path_mae"]
        lines.append(f"Path MAE (daily linear interpolation): d {fmt(pm['wsmDia'])} mm · f {fmt(pm['wsmFlange'])} mm · r {fmt(pm['wsmRoot'])} mm")
        # noise/coverage context
        notes = []
        for d in DIM_ORDER:
            sigma = NOISE[d]["central_sigma_mm"]
            h, w = nearest_width(d, target_day)
            pred, act = r["pred_at"][d], r["actual"][d]
            inside = abs(act - pred) <= w
            notes.append(f"{DIM_LBL[d]}: |res|/σ={abs(r['residual'][d]) / sigma:.1f}, 80% band ±{fmt(w)} {h}d {'covers' if inside else 'misses'}")
        lines.append(f"Residual vs measurement noise σ: " + "; ".join(notes))
        pt = r.get("pturn") or {}
        lines.append(f"Model P(turn) at T: 30d {ptfmt(pt.get('30'))} · 60d {ptfmt(pt.get('60'))} · 90d {ptfmt(pt.get('90'))}")
        lines.append("")
    else:
        day = r["turn_day"]
        lines.append(f"### {ws} — LOCO {loco} / shed {shed}  ·  {risk_lbl}  ·  TURN-crossing interval")
        lines.append("")
        lines.append(f"Prediction time T = **{r['anchor_ts']}**  (last valid WSM, quality = OBSERVED_VALID)")
        feats = ", ".join(r["features"][:6]) + ", …"
        lines.append(f"Features used: *[{feats}]*  (feature coverage {fmt(r['fr_cov'] * 100, 0)}%)")
        lines.append("")
        lines.append(f"No-turn forecast at T+{day} d (turn completes **{r['turn_ts']}**):")
        for d in DIM_ORDER:
            lines.append(f"  {DIM_LBL[d]}̂ = {fmt(r['pred_no_turn_at_turn'][d])} mm")
        lines.append("")
        lines.append(f"ACTUAL next state = post-turn restored measurement ({r['turn_ts']}, quality = {r['quality_post_turn'].replace('valid', 'OBSERVED_VALID')}):")
        for d in DIM_ORDER:
            lines.append(f"  {DIM_LBL[d]} = {fmt(r['actual_post_turn'][d])} mm")
        lines.append("")
        lines.append("Residual vs the no-turn forecast (dominated by the discrete reset, not continuous drift):")
        rr = r["residual"]
        lines.append("  " + ", ".join(f"Δ{DIM_LBL[d]} = {rr[d]:+.2f} mm" for d in DIM_ORDER))
        st = r["restore"]
        lines.append("")
        lines.append(f"Recorded restoration operator (engineering rule, from lifecycle_turns):")
        lines.append(f"  cut_dia = {fmt(st['cut_dia'], 1)} mm (pre {fmt(st['pre_wsmDia'], 1)} → post {fmt(st['post_wsmDia'], 1)})")
        lines.append(f"  post-flange = {fmt(st['post_wsmFlange'], 2)} mm · post-root = {fmt(st['post_wsmRoot'], 2)} mm")
        lines.append("")
        pt = r.get("pturn") or {}
        lines.append(f"Model P(turn) at T: 30d {ptfmt(pt.get('30'))} · 60d {ptfmt(pt.get('60'))} · 90d {ptfmt(pt.get('90'))}  (turn DID occur; no turn-conditional head exists)")
        lines.append("")
    return "\n".join(lines)


HDR = """# Next-State Prediction — Senior Walkthrough (6 concrete wheel-level examples)

**What this set is.** Strict point-in-time replays on the serving degradation head:
features are frozen at measurement time T, the 30/90/180d no-turn forecast path is
evaluated against what actually happened later. Two kinds of interval:

- **NO-TURN** — the next same-segment measurement (pure continuous degradation accuracy).
- **TURN** — a confirmed lifecycle turn completes inside the horizon: the no-turn
  forecast is compared against the *post-turn restored* state, and the recorded
  restoration operator (cut depth, restored flange/root) is shown separately.

Each wheel is labelled by risk (HIGH = P(turn)90d ≥ 1% or ≤180d to condemning) and shed.
Model artifacts: degradation head `v{version}` (delta mode), train cutoff `{cutoff}`.
Residuals are only computed on `OBSERVED_VALID` row-measurements; no clipping.
Risk labels are as-of the current risk-card snapshot (not at T); the wheelset's own
P(turn) at T is printed per block.

## Evaluation protocol (per wheel)

| Quantity | Definition |
| --- | --- |
| Prediction time T | last observed measurement used as input features |
| Horizon Δ | days to next observed measurement (no-turn) or to the turn event (turn) |
| Predicted state ŝ_{{T+Δ}} | model output on the no-turn path (piecewise-linear 30/90/180) |
| Actual state s_{{T+Δ}} | subsequent WSM measurement (or post-turn restored measurement) |
| Residual | s − ŝ per dimension |
| Turn-aware residual | no-turn path residual on turn intervals + recorded restore operator |
"""


def main():
    body = [HDR.format(version=D[0]["model_version"], cutoff=D[0]["train_cutoff"])]
    for i, r in enumerate(D, 1):
        body.append(block(r))
    notes = {
        "406356": "re-provision at T not split → false no-turn (flag case)",
        "406320": "dia flat in reality vs predicted decline; wear dims ≈ σ",
        "30792": "wear dims excel; dia conservatively over-declines",
        "439629": "root grows far faster than head forecasts (fast-wear)",
        "406950": "no-turn path invalidated by 13 mm cut (reset, not drift)",
        "406083": "high root → restored to 0.35 mm; reset dominates",
    }
    rows = []
    for i, r in enumerate(D, 1):
        ws = str(r["ws"])
        kind = r["kind"]
        if kind == "no_turn":
            delta_days = r["target_day"]
            dd = f"{r['residual']['wsmDia']:+.2f}"
            df = f"{r['residual']['wsmFlange']:+.2f}"
            dr = f"{r['residual']['wsmRoot']:+.2f}"
            pm = fmt(r["path_mae"]["wsmDia"])
            rtyp = "no-turn"
        else:
            delta_days = r["turn_day"]
            dd = f"{r['residual']['wsmDia']:+.2f}"
            df = f"{r['residual']['wsmFlange']:+.2f}"
            dr = f"{r['residual']['wsmRoot']:+.2f}"
            pm = "—"
            rtyp = "turn"
        rows.append(
            f"| {i} | {ws} | {r['shed']} | {risk(r)} | {rtyp} | {int(delta_days)} | {dd} | {df} | {dr} | {pm} | {notes.get(ws, '')} |"
        )
    table = "## Head-to-head\n\n| # | ws | shed | risk | type | Δ(days) | Δd | Δf | Δr | Path MAE d | read |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows)

    body.append(table)
    body.append("""
## What the senior should conclude

1. **Wear dims (root/flange/thread) on no-turn intervals are close to usable.** Example 3 shows
   residuals at or below the measurement-noise σ (0.10–0.11 mm); example 2 flange 0.07 mm vs σ 0.11.
   The continuous head is NOT uniformly weak — the top-N ranking only needs relative order, and
   on many no-turn intervals the geometric level is also accurate to ~σ.

2. **Diameter is where the continuous head is systematically conservative.** On flat wheelsets it
   forecasts decline that did not happen (+2.1 to +2.7 mm at ~30d are ~40–50× the σ=0.05 mm noise
   floor, but inside the calibrated 80% band width of ±3.2 mm). Direction is right; magnitude is
   over-confident. Fixing this is tighter conditioning on the most recent profile shape, not a
   new end-to-end sequence model.

3. **Fast-wear wheelsets (high P(turn)) are under-forecast on root.** Example 4: model emits
   +0.4 mm root over 40d; actual root +2.35 mm. The hazard head ranks these wheelsets correctly,
   but the level head under-predicts the very attrition that drives the ranking — a concrete
   separation of the two heads in action.

4. **Turn-crossing intervals are a discrete operator, not a regression failure.** Examples 5–6:
   the no-turn path is off by −8.3 mm dia (13 mm cut) and −1.9 mm root (restore to 0.35 mm).
   A next-state head that "continues the plot" must condition on the turn indicator or emit
   two conditional forecasts (turn vs no-turn) — otherwise the post-turn restoration error
   masquerades as degradation error.

5. **Quality stratification is material.** Example 1 carries an unflagged re-provision at T
   (wsmProvDate moves to T with no segment split) — the segment boundary logic treats it as
   continuation and produces a −4.8 mm dia residual. Residuals must be reported on
   OBSERVED_VALID only AND flagged where a boundary was suspected, or short-horizon residuals
   are polluted by the very reset operator the head does not model.

> Reproducibility: machine-readable pulls in `_walkthrough_pull.json` (repo root). Cells above
> come from `backtest.wheelset_replay` (strict point-in-time) + the trajectory-conformal artefact.
""")
    md = "\n".join(body)
    with open(r"C:\Users\CRIS\Desktop\ayush\wheel-project\NEXT_STATE_WALKTHROUGH.md", "w", encoding="utf-8") as f:
        f.write(md)
    print("wrote", len(md), "chars")


if __name__ == "__main__":
    main()