"""Phase 5 Layer 3 - turning/profile policy substrate (the B-A cut model).

Assembles a point-in-time training table from the Layer-0 turn events
(lifecycle_turns_shed.parquet). Each row = one turning event. The predicted
outcome is the machining action itself (cut = pre_dia - post_dia) plus the
post-turn residual state, conditioned on pre-turn state, shed policy, profile
class, position and prior-turn history - i.e. post_turn_wear ~ A + eps, and the
recovered per-shed "B - A" policy (per-shed systematic cut).

Split: temporal PIT by pre_ts (train strictly before the cutoff date), so that
shed-policy lookups and model refits never leak post-cutoff information.

Output: model_datasets/v5/turn_policy_benchmark.parquet + manifest json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "model_datasets" / "v5" / "lifecycle_turns_shed.parquet"
OUT_DIR = ROOT / "model_datasets" / "v5"
OUT = OUT_DIR / "turn_policy_benchmark.parquet"
MANIFEST = OUT_DIR / "turn_policy_manifest.json"

TRAIN_CUTOFF = pd.Timestamp("2024-08-12")

NUM = ["pre_wsmDia", "pre_wsmFlange", "pre_wsmRoot", "pre_wsmThread",
       "days_between", "segment_index"]
CAT = ["shed_any", "wheel_profile_2class", "wheel_position_1_12"]
TARGETS = ["cut_dia", "post_wsmDia", "post_wsmFlange", "post_wsmRoot",
           "post_wsmThread"]


def main() -> None:
    tr = pd.read_parquet(SRC)
    t = pd.to_datetime(tr["pre_ts"])
    tr = tr.assign(pre_ts=t, train=t < TRAIN_CUTOFF)

    feats = tr[["pre_ts", "train"] + NUM + CAT + TARGETS].copy()
    feats["month"] = t.dt.month
    feats["year"] = t.dt.year

    for c in NUM + TARGETS:
        feats[c] = pd.to_numeric(feats[c], errors="coerce")
    feats = feats.replace([np.inf, -np.inf], np.nan)

    n = len(feats)
    disc = feats["cut_dia"].isna().sum()
    tmp = feats.to_dict("records")
    rng = lambda s: dict(mean=round(float(np.nanmean(s)), 3),
                         std=round(float(np.nanstd(s)), 3))
    stats = {
        "shed_policy": int(feats.loc[feats.train, "shed_any"].nunique()),
        "profile_classes": int(feats["wheel_profile_2class"].nunique()),
        "target_stats": {c: rng(feats[c]) for c in TARGETS},
    }

    feats.to_parquet(OUT, index=False)
    (MANIFEST).write_text(json.dumps({
        "task": "phase5 layer3 turn-policy substrate",
        "source": str(SRC.relative_to(ROOT)),
        "output": str(OUT.relative_to(ROOT)),
        "n_rows": int(n),
        "n_train": int(feats.train.sum()),
        "n_test": int((~feats.train).sum()),
        "train_cutoff": str(TRAIN_CUTOFF.date()),
        "shed_events_discarded_frac": round(float(disc / n), 4),
        "numeric_features": NUM,
        "categorical_features": CAT,
        "targets": TARGETS,
        "stats": stats,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"turns {n:,}  train={int(feats.train.sum()):,} "
          f"test={int((~feats.train).sum()):,}")
    print("sheds(train, >0 events):",
          feats.loc[feats.train, "shed_any"].nunique())
    print(MANIFEST.relative_to(ROOT))


if __name__ == "__main__":
    main()