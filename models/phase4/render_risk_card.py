"""Phase 4 - Wheel Risk Card renderer (plan section 9, Stage 4-D).

Renders the per-inspection artifact combining both 90-day risks (root
constraint + maintenance/turning realization), limiting dimension, current
state, likely contributors (SHAP), action, and a calibration band.

Usage:
  python models/phase4/render_risk_card.py [measurement_record_id]

If no id is given, renders the highest combined-risk wheel of the scored batch.
Output: prints the card to stdout and writes a .txt copy under
        models/experiments/v4/risk_cards/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "models" / "experiments" / "v4"

BAR = "█"; EMPTY = "░"
RISK_BAR = {"HIGH": 12, "MEDIUM": 7, "LOW": 3}
LIMIT_ROOT = 3.0


def bar(level: str) -> str:
    n = RISK_BAR[level]
    return BAR * n + EMPTY * (12 - n)


def render(mr_id) -> str:
    root = pd.read_parquet(OUTPUT / "wheel_attribution_root.parquet")
    turn = pd.read_parquet(OUTPUT / "wheel_attribution_turn.parquet")
    r = root[root["measurement_record_id"] == mr_id]
    t = turn[turn["measurement_record_id"] == mr_id]
    if r.empty or t.empty:
        raise SystemExit(f"measurement_record_id {mr_id} not in scored batch")
    r = r.iloc[0]; t = t.iloc[0]

    action = ("→ PRIORITY INSPECTION" if (r.risk == "HIGH" or t.risk == "HIGH")
              else "→ SCHEDULE INSPECTION" if (r.risk == "MEDIUM" or t.risk == "MEDIUM")
              else "→ ROUTINE MONITORING")

    def top(c, n=4):
        return "  ".join(f"{i+1} {c['label']}" for i, c in enumerate(c[:n]))

    root_margin = LIMIT_ROOT - r.wsmRoot_mean if np.isfinite(r.wsmRoot_mean) else None
    limiting = f"ROOT (margin {root_margin:+.2f} mm)" if root_margin is not None else "ROOT"
    conf = t.conf_empirical_rate if np.isfinite(t.conf_empirical_rate) else r.conf_empirical_rate
    conf_txt = (f"calibrated band: ~{conf*100:.0f}% 90d event rate "
                f"(decile {t.conf_decile}/10, train)") if conf is not None else "n/a"

    lines = [
        "WHEEL ENGINEERING RISK CARD",
        f"Wheelset {r.wheelset_equipment_id} / Loco {r.locomotive_id} / {pd.Timestamp(r.measurement_timestamp).date()}",
        f"90-DAY MAINTENANCE RISK          {bar(t.risk)}  {t.risk}",
        f"ROOT CONSTRAINT RISK             {bar(r.risk)}  {r.risk}",
        f"LIMITING DIMENSION               {limiting}",
        f"CURRENT STATE                    Dia {r.wsmDia_mean:.1f} / Root {r.wsmRoot_mean:.2f} / "
        f"Flange {r.wsmFlangeThickness_mean:.2f} / Gauge {r.wsmWheelGauge_mean:.2f} (mm)",
        f"LIKELY CONTRIBUTORS              {top(r.contributors)}",
        f"                                  {top(t.contributors)}",
        f"ACTION                           {action}",
        f"MODEL CONFIDENCE                 {conf_txt}",
    ]
    return "\n".join(lines)


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg is None:
        root = pd.read_parquet(OUTPUT / "wheel_attribution_root.parquet")
        turn = pd.read_parquet(OUTPUT / "wheel_attribution_turn.parquet")
        r = root[root["risk"] == "HIGH"]
        t = turn[turn["risk"] == "HIGH"]
        common = pd.merge(r, t, on="measurement_record_id", suffixes=("_r", "_t"))
        if not common.empty:
            common["combined"] = common["prob_r"] + common["prob_t"]
            mr_id = common.sort_values("combined", ascending=False).iloc[0].measurement_record_id
        else:
            both = pd.merge(root, turn, on="measurement_record_id", suffixes=("_r", "_t"))
            both["combined"] = both["prob_r"] + both["prob_t"]
            mr_id = both.sort_values("combined", ascending=False).iloc[0].measurement_record_id
    else:
        mr_id = int(arg)

    card = render(mr_id)
    outdir = OUTPUT / "risk_cards"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"risk_card_{mr_id}.txt"
    out.write_text(card + "\n", encoding="utf-8")
    print(card.encode("utf-8", "replace").decode("utf-8"))
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
