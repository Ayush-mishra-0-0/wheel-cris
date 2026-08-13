"""Profile Wheel Engineering State source fields for Phase 3.

This report profiles measured-state availability and documented plausibility
windows.  It deliberately does not calculate engineering margins or a health
score: those require approved stock/profile-specific limits.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
OUTPUT = ROOT / "models" / "experiments" / "v3" / "engineering_state_profile"

DIMENSIONS = {
    "diameter": {"columns": ["wsmDia1", "wsmDia2"], "range": [1000.0, 1100.0], "status": "MEASURED_READY_WITH_CAVEAT", "meaning": "Tread diameter; unit and range are supported by existing owner constants, but stock/profile applicability remains to be versioned."},
    "flange_thickness": {"columns": ["wsmFlangeThickness1", "wsmFlangeThickness2"], "range": [10.0, 50.0], "status": "MEASURED_READY_WITH_CAVEAT", "meaning": "Direct flange-thickness measurement; no approved intervention limit in the repository."},
    "root": {"columns": ["wsmRoot1", "wsmRoot2"], "range": [0.0, 30.0], "status": "MEASURED_READY_WITH_CAVEAT", "meaning": "Direct root/fillet measurement with repeatability variance; no approved limit."},
    "tire_thickness": {"columns": ["wsmTireThikness1", "wsmTireThikness2"], "range": [5.0, 100.0], "status": "MEASURED_READY_WITH_CAVEAT", "meaning": "Measured tire-thickness field; convention and coupling to diameter remain unapproved."},
    "wheel_gauge": {"columns": ["wsmWheelGauge1", "wsmWheelGauge2"], "range": [1300.0, 1700.0], "status": "MEASURED_WHEELSET_CONTEXT", "meaning": "Likely wheelset/back-to-back assembly geometry, not a per-wheel wear measure."},
    "flange_unknown": {"columns": ["wsmFlange1", "wsmFlange2"], "range": None, "status": "SEMANTICS_BLOCKED", "meaning": "Physical meaning is unresolved: possible flange height, code, or legacy field."},
    "tread_unknown": {"columns": ["wsmThread1", "wsmThread2"], "range": None, "status": "SEMANTICS_BLOCKED", "meaning": "Likely tread/hollow measurement, but physical definition and direction are unresolved."},
    "profile_parameters_unknown": {"columns": ["wsmKvalue1", "wsmSDistance1"], "range": None, "status": "SEMANTICS_BLOCKED", "meaning": "Potential profile parameters; QR relationship is unconfirmed."},
}


def main() -> None:
    columns = ["wsmId", "wsmEquipmentId", "wsmUpdatedOn", "wsmturning1", "wsmturning2", "wsmSkidTurn1", "wsmSkidTurn2"]
    columns.extend(column for d in DIMENSIONS.values() for column in d["columns"])
    df = pd.read_parquet(SOURCE, columns=columns)
    profile: dict[str, object] = {"source": str(SOURCE.relative_to(ROOT)), "n_measurements": int(len(df)), "dimensions": {}}
    for name, spec in DIMENSIONS.items():
        summary = {"status": spec["status"], "meaning": spec["meaning"], "columns": {}}
        for column in spec["columns"]:
            values = pd.to_numeric(df[column], errors="coerce")
            nonnull = values.notna()
            item = {"nonnull_n": int(nonnull.sum()), "nonnull_pct": float(nonnull.mean())}
            if spec["range"] is not None:
                lower, upper = spec["range"]
                valid = values.between(lower, upper)
                item.update({"plausible_range": [lower, upper], "plausible_n": int(valid.sum()), "plausible_pct_of_nonnull": float(valid[nonnull].mean()) if nonnull.any() else None, "median_plausible": float(values[valid].median()) if valid.any() else None})
            else:
                item.update({"plausible_range": None, "median_nonnull": float(values[nonnull].median()) if nonnull.any() else None})
            summary["columns"][column] = item
        profile["dimensions"][name] = summary
    turn1 = df["wsmturning1"].eq(1)
    profile["event_context"] = {"turn1_rows": int(turn1.sum()), "turn1_rate": float(turn1.mean()), "skid_turn1_nonzero_rows": int(df["wsmSkidTurn1"].fillna("").astype(str).str.strip().isin(["1", "1.0"]).sum())}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "engineering_state_profile.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    lines = ["# Wheel Engineering State — Source Profile", "", f"Source measurements: {len(df):,}", "", "| Dimension | State status | Side-1 plausible coverage | Side-2 plausible coverage |", "| --- | --- | ---: | ---: |"]
    for name, summary in profile["dimensions"].items():
        cols = list(summary["columns"].values())
        def coverage(item: dict) -> str:
            return f"{item['plausible_pct_of_nonnull']:.1%}" if item.get("plausible_pct_of_nonnull") is not None else "not defined"
        lines.append(f"| {name} | {summary['status']} | {coverage(cols[0])} | {coverage(cols[1]) if len(cols) > 1 else 'n/a'} |")
    lines += ["", "Plausibility windows are data-quality filters from the existing degradation-semantics audit, not condemning limits. No margin or health score is calculated by this profile."]
    (OUTPUT / "engineering_state_profile_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
