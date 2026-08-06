"""Phase 2 gating artifact — per-year feature availability report.

Before any benchmark runs, quantify when each feature family is actually
observable. The Phase-1 finding is that the RTIS daily ledger only exists
2023-02 -> 2025-12 and FOIS only 2025-10 -> 2026-06, while the dataset spans
2014-2026. A feature whose coverage is concentrated at the tail of the time
range is a *time-marker*, not a mechanism, and any importance/ablation number
on it is confounded with "when in history the row lives".

Output:
  models/experiments/v2/feature_availability/per_year_availability.parquet
  models/experiments/v2/feature_availability/feature_availability_report.md

Grain: family x calendar year (by interval_end_timestamp); fraction non-null.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from models.phase2.families import FAMILY_LABELS, FAMILY_ORDER, feature_families  # noqa: E402

DATASET = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_v2.0.parquet"
MANIFEST = PROJECT_ROOT / "model_datasets" / "v2" / "model_dataset_manifest_v2.0.json"
OUT_DIR = PROJECT_ROOT / "models" / "experiments" / "v2" / "feature_availability"

REGRESSION_LABEL = "next_interval_dia_delta_mm"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = pd.read_parquet(DATASET)
    fams = feature_families(MANIFEST)
    year = pd.to_datetime(dataset["interval_end_timestamp"]).dt.year

    rows = []
    for fam in FAMILY_ORDER:
        cols = fams[fam]
        for y in sorted(year.unique()):
            mask = year == y
            frac = float(dataset.loc[mask, cols].notna().mean().mean()) if mask.any() else np.nan
            rows.append({"family": fam, "family_label": FAMILY_LABELS[fam],
                         "year": int(y), "n_intervals": int(mask.sum()),
                         "non_null_fraction": round(frac, 4)})
    avail = pd.DataFrame(rows)

    label_avail = dataset.groupby(year)[REGRESSION_LABEL].apply(lambda s: s.notna().mean())
    label_avail = label_avail.rename("label_non_null_fraction").reset_index()
    label_avail.columns = ["year", "label_non_null_fraction"]

    avail.to_parquet(OUT_DIR / "per_year_availability.parquet", index=False)

    pivot = avail.pivot(index="year", columns="family", values="non_null_fraction").reindex(
        columns=FAMILY_ORDER)
    label_map = dict(zip(label_avail["year"], label_avail["label_non_null_fraction"]))

    lines = [
        "# Feature availability by calendar year (v2.0, gating artifact)",
        "",
        "Read BEFORE interpreting any benchmark/importance/ablation number. A family that",
        "appears only in recent years is a **time-marker** (its values say *when* the row",
        "lives), not a mechanism. Fraction of intervals with non-null value per year.",
        "",
        "| year | n | label | " + " | ".join(FAMILY_ORDER) + " |",
        "| ---: | ---: | ---: |" + " ---: |" * len(FAMILY_ORDER),
    ]
    for y, r in pivot.iterrows():
        lab = f"{label_map.get(int(y), float('nan')):.3f}"
        cells = " | ".join(f"{v:.3f}" if pd.notna(v) else "—" for v in r)
        lines.append(f"| {int(y)} | {int(year.eq(y).sum()):,} | {lab} | {cells} |")

    # Time-marker flag: family whose earliest non-null year is late.
    lines += [
        "",
        "## Time-marker diagnosis (family level)",
        "",
        "| family | earliest year with >5% coverage | coverage at that year |",
        "| --- | ---: | ---: |",
    ]
    for fam in FAMILY_ORDER:
        sub = avail[avail["family"] == fam]
        strong = sub[sub["non_null_fraction"] > 0.05]
        if len(strong):
            first = strong.sort_values("year").iloc[0]
            lines.append(f"| {fam} | {int(first['year'])} | {first['non_null_fraction']:.3f} |")
        else:
            lines.append(f"| {fam} | never | — |")

    # Per-column diagnosis for the mechanism columns in the Phase-2 families
    # (the family mean is diluted by always-present metadata columns).
    mech_cols = {
        "exposure_v2": ["interval_distance_km", "distance_per_day_km",
                        "distance_since_last_inspection_km", "running_hours_proxy",
                        "distance_since_turning_km", "maintenance_density_per_1000km"],
        "physics_v2": ["wear_per_1000km_s1", "remaining_material_per_km_s1",
                       "projected_remaining_km_s1", "exposure_index_s1"],
    }
    lines += [
        "",
        "## Time-marker diagnosis (mechanism columns, per column)",
        "",
        "The family-level fraction above is diluted by always-present metadata columns",
        "(coverage days, running_days, maintenance_density_per_day). These mechanism",
        "columns are the ones whose availability shifts with the source windows:",
        "",
        "| column | earliest year with >5% coverage | coverage at that year | last-year coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for fam, cols in mech_cols.items():
        for col in cols:
            sub = pd.DataFrame({
                "year": [y for y in sorted(year.unique())],
                "frac": [float(dataset.loc[year == y, col].notna().mean()) if (year == y).any() else np.nan
                         for y in sorted(year.unique())],
            })
            strong = sub[sub["frac"] > 0.05]
            if len(strong):
                first = strong.sort_values("year").iloc[0]
                last_frac = sub.sort_values("year").iloc[-1]["frac"]
                lines.append(f"| {col} | {int(first['year'])} | {first['frac']:.3f} | {last_frac:.3f} |")
            else:
                lines.append(f"| {col} | never | — | — |")

    lines += [
        "",
        "## Interpretation",
        "",
        "- `interval_distance_km`, `wear_per_1000km_*`, `distance_per_day_km` are **0% before",
        "  2023** and ~80-92% in 2023-2025: any importance/ablation on them is entangled with",
        "  the RTIS-window boundary. In the grouped temporal split, train rows (2014-2021) are",
        "  almost all missing them, so the model can only exploit them on recent rows.",
        "- `running_hours_proxy` is a **pure time-marker** (0% until 2025, 90% in 2026): treat",
        "  any signal it carries as suspect until a non-window-confounded source exists.",
        "- `physics_v2` (WS3) rides entirely on the same RTIS window -> same caveat.",
        "- Mitigation used in WS4/WS5: report availability-normalized arms and call out",
        "  time-confounded families explicitly instead of claiming mechanistic value.",
    ]
    (OUT_DIR / "feature_availability_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {OUT_DIR / 'feature_availability_report.md'}")
    print(pivot.round(3).to_string())


if __name__ == "__main__":
    main()
