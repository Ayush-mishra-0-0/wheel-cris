"""Build immutable Phase 3 Wheel Engineering State v1.0.

The dataset is a measured-state layer only. It intentionally contains no
engineering margins, health score, latent-need label, or future outcome.
"""
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "bronze" / "wheel_measurements.parquet"
TIMELINE = ROOT / "data" / "gold" / "business_truth" / "v1.0" / "wheel_timeline_gold_b.parquet"
FEATURE_STORE = ROOT / "feature_store" / "feature_store_v1.parquet"
OUTPUT_DIR = ROOT / "model_datasets" / "v3"

QUALITY_WINDOWS = {
    "wsmDia1": (1000.0, 1100.0), "wsmDia2": (1000.0, 1100.0),
    "wsmFlangeThickness1": (10.0, 50.0), "wsmFlangeThickness2": (10.0, 50.0),
    "wsmRoot1": (0.0, 30.0), "wsmRoot2": (0.0, 30.0),
    "wsmTireThikness1": (5.0, 100.0), "wsmTireThikness2": (5.0, 100.0),
    "wsmWheelGauge1": (1300.0, 1700.0), "wsmWheelGauge2": (1300.0, 1700.0),
}
BLOCKED_FIELDS = ("wsmFlange1", "wsmFlange2", "wsmThread1", "wsmThread2", "wsmKvalue1", "wsmSDistance1")


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quality_code(values: pd.Series, low: float, high: float) -> pd.Series:
    return pd.Series("OBSERVED_VALID", index=values.index, dtype="string").mask(values.isna(), "MISSING").mask(values.notna() & ~values.between(low, high), "IMPLAUSIBLE")


def main(version: str = "v1.0") -> None:
    output = OUTPUT_DIR / f"wheel_engineering_state_{version}.parquet"
    manifest_path = OUTPUT_DIR / f"wheel_engineering_state_manifest_{version}.json"
    card_path = OUTPUT_DIR / f"wheel_engineering_state_card_{version}.md"
    if any(path.exists() for path in (output, manifest_path, card_path)):
        raise FileExistsError(f"Wheel Engineering State {version} already exists; create a new version instead of overwriting it.")
    raw_columns = ["wsmId", *QUALITY_WINDOWS.keys(), *BLOCKED_FIELDS, "wsmturning1", "wsmturning2", "wsmSkidTurn1", "wsmSkidTurn2", "wsmProvDate"]
    raw = pd.read_parquet(RAW, columns=raw_columns).rename(columns={"wsmId": "measurement_record_id"})
    timeline_columns = ["measurement_record_id", "wheelset_equipment_id", "measurement_timestamp", "quality_flags", "record_status", "timeline_quality_tier", "locomotive_id", "LomNumber", "LocoType"]
    state = pd.read_parquet(TIMELINE, columns=timeline_columns).merge(raw, on="measurement_record_id", how="left", validate="one_to_one")
    for column, (low, high) in QUALITY_WINDOWS.items():
        state[f"{column}_quality"] = quality_code(pd.to_numeric(state[column], errors="coerce"), low, high)
    for column in BLOCKED_FIELDS:
        state[f"{column}_quality"] = pd.Series("SEMANTICS_BLOCKED", index=state.index, dtype="string").mask(state[column].isna(), "MISSING")
    state["turning_record_at_measurement"] = state["wsmturning1"].eq(1).astype("int8")
    state["turning_side_disagreement"] = (state["wsmturning1"].eq(1) ^ state["wsmturning2"].eq(1)).astype("int8")
    state["skid_turn_record_at_measurement"] = state["wsmSkidTurn1"].fillna("").astype(str).str.strip().isin(["1", "1.0"]).astype("int8")

    fs_columns = ["interval_end_measurement_id", "operational_exposure_id", "interval_days", "rtis_source_event_count", "rtis_source_event_type_count", "maintenance_jobcard_creation_count", "rtis_reporting_coverage_pct", "rtis_report_count", "rtis_reporting_days", "rtis_duplicate_report_count", "wheel_position_1_12", "axle_position_1_6", "wheel_profile_2class", "wheel_schedule_id", "home_shed", "defect_zone", "defect_division", "wheel_age_days_proxy", "wheel_age_date_source", "days_since_turning"]
    context = pd.read_parquet(FEATURE_STORE, columns=fs_columns).rename(columns={"interval_end_measurement_id": "measurement_record_id"})
    state = state.merge(context, on="measurement_record_id", how="left", validate="one_to_one")
    state["interval_context_available"] = state["operational_exposure_id"].notna().astype("int8")
    state = state.sort_values(["wheelset_equipment_id", "measurement_timestamp", "measurement_record_id"]).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state.to_parquet(output, index=False)
    manifest = {
        "dataset_version": f"wheel_engineering_state_{version}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "grain": "one Gold-B attributable inspection measurement",
        "rows": int(len(state)),
        "columns": int(len(state.columns)),
        "input_sha256": {"raw_measurements": checksum(RAW), "timeline_gold_b": checksum(TIMELINE), "feature_store_v1": checksum(FEATURE_STORE)},
        "state_semantics": "Measured engineering state and point-in-time context only; no margin, health score, latent engineering need, or future outcome is materialised.",
        "quality_windows": QUALITY_WINDOWS,
        "blocked_fields": list(BLOCKED_FIELDS),
        "context_available_rows": int(state["interval_context_available"].sum()),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    quality_columns = [column for column in state if column.endswith("_quality")]
    lines = [
        f"# Wheel Engineering State {version}", "",
        f"- **Rows:** {len(state):,}",
        f"- **Columns:** {len(state.columns):,}",
        "- **Grain:** one Gold-B attributable inspection measurement.",
        "- **Scope:** measured engineering state plus point-in-time-safe context; no engineering margins or target labels.",
        f"- **Interval context available:** {state['interval_context_available'].mean():.1%}", "",
        "## Quality-code coverage", "", "| field quality code | OBSERVED_VALID | MISSING | IMPLAUSIBLE / BLOCKED |", "| --- | ---: | ---: | ---: |",
    ]
    for column in quality_columns:
        counts = state[column].value_counts(dropna=False)
        valid = int(counts.get("OBSERVED_VALID", 0))
        missing = int(counts.get("MISSING", 0))
        other = int(len(state) - valid - missing)
        lines.append(f"| {column} | {valid:,} | {missing:,} | {other:,} |")
    lines += ["", "Plausibility windows are data-quality filters, not condemning limits. See `docs/wheel_engineering_state_specification_v1.0.md`."]
    card_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1.0", help="Version suffix, e.g. v1.1; existing artifacts are never overwritten.")
    main(parser.parse_args().version)
