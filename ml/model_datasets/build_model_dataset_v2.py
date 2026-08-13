"""Model Dataset builder v2.0 — Phase 2 (WS1 exposure + WS3 physics features).

EXTENDS the immutable v1.2 chain (build_model_dataset_v1_2.py): the v1.2 dataset
is loaded UNCHANGED (byte-identical 96-feature X block, same split assignment,
same labels) and the Phase-2 columns are APPENDED:

  WS1 Operational Exposure (from model_datasets/build_exposure_features_v2.py):
    interval_distance_km, rtis_distance_coverage_days/pct_in_interval,
    distance_per_day_km, distance_since_last_inspection_km, running_days,
    running_days_pct, running_hours_proxy, maintenance_density_per_day,
    maintenance_density_per_1000km, distance_since_turning_km

  WS3 Physics-informed (derived here from v1.2 columns + WS1 distance):
    wear_per_1000km_s1/s2          clean-interval material loss per 1000 km
                                   (mm/1000km; only intervals with NO turning at
                                   the interval-end measurement — otherwise the
                                   delta is a turning step, not wear)
    remaining_material_per_km_s1/s2  phys_remaining_material_mm / distance_since_turning_km
    projected_remaining_km_s1/s2     remaining material / wear-per-km (lifetime estimate)
    exposure_index_s1/s2             (distance_since_turning_km/1000) * phys_wear_fraction
                                   (distance exposure weighted by material consumed)

Governance:
  - interval_distance_km_experimental is left UNRENAMED/untouched.
  - Wear-derived features are EXPERIMENTAL: they depend on the engineering
    wear definition (docs/degradation_semantics.md) and remain out of the
    released Feature Store contract until sign-off. Status is recorded per
    column in DATA_ADDITIONS.json.
  - The new columns carry EXPECTED missingness (RTIS window starts 2023-02-06;
    running-hours proxy is FOIS-window limited). The v1.2 "X fully populated"
    gate is therefore applied ONLY to the original X block.

Every new column is point-in-time safe (uses only data at or before
interval_end_timestamp).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from silver_gold.transform import _sha256  # noqa: E402

V1_2_DIR = PROJECT_ROOT / "model_datasets" / "v1.2"
V1_2_DATASET = V1_2_DIR / "model_dataset_v1.2.parquet"
V1_2_MANIFEST = V1_2_DIR / "model_dataset_manifest_v1.2.json"
EXPOSURE_PATH = PROJECT_ROOT / "model_datasets" / "v2" / "exposure_features_v2.parquet"
OUT_DIR = PROJECT_ROOT / "model_datasets" / "v2"

DATASET_VERSION = "v2.0"
PARENT_VERSION = "v1.2"

EXPOSURE_COLUMNS = [
    "interval_distance_km", "rtis_distance_coverage_days_in_interval",
    "rtis_distance_coverage_pct_in_interval", "distance_per_day_km",
    "distance_since_last_inspection_km", "running_days", "running_days_pct",
    "running_hours_proxy", "maintenance_density_per_day",
    "maintenance_density_per_1000km", "distance_since_turning_km",
]

# Per-side physics inputs present in v1.2.
SIDES = {
    "s1": {"delta": "diameter_delta_raw_mm_side_1", "remaining": "phys_remaining_material_mm_s1",
           "frac": "phys_wear_fraction_s1"},
    "s2": {"delta": "diameter_delta_raw_mm_side_2", "remaining": "phys_remaining_material_mm_s2",
           "frac": "phys_wear_fraction_s2"},
}


def _physics_features(dataset: pd.DataFrame, exposure: pd.DataFrame) -> pd.DataFrame:
    dist_km = exposure["interval_distance_km"].to_numpy(dtype=np.float64)
    dist_turn = exposure["distance_since_turning_km"].to_numpy(dtype=np.float64)
    turning = pd.to_numeric(dataset["turning_indicator_raw"], errors="coerce").to_numpy(dtype=np.float64)
    out = pd.DataFrame(index=dataset.index)

    for side, cols in SIDES.items():
        delta = pd.to_numeric(dataset[cols["delta"]], errors="coerce").to_numpy(dtype=np.float64)
        remain = pd.to_numeric(dataset[cols["remaining"]], errors="coerce").to_numpy(dtype=np.float64)
        frac = pd.to_numeric(dataset[cols["frac"]], errors="coerce").to_numpy(dtype=np.float64)

        # wear_per_1000km: clean interval (no turning at END) over a genuine
        # RUNNING interval (>= 50 km attributable distance). Shorter intervals are
        # shed/stabling movements where a small delta is measurement noise, not wear.
        clean = (turning == 0) & np.isfinite(delta) & (dist_km >= 50.0)
        wear = np.abs(delta) / (dist_km / 1000.0)
        out[f"wear_per_1000km_{side}"] = np.where(clean, wear, np.nan)

        # remaining_material_per_km: remaining material per km run since turning.
        ok_turn = np.isfinite(dist_turn) & (dist_turn > 0)
        out[f"remaining_material_per_km_{side}"] = np.where(
            ok_turn & np.isfinite(remain), remain / dist_turn, np.nan)

        # projected_remaining_km: remaining material / wear-per-km (lifetime left).
        wear_km = wear  # already mm/1000km -> /1000 gives mm/km
        out[f"projected_remaining_km_{side}"] = np.where(
            clean & (wear_km > 0) & np.isfinite(remain), remain / (wear_km / 1000.0), np.nan)

        # exposure_index: distance-since-turning (in 1000 km) weighted by material fraction used.
        out[f"exposure_index_{side}"] = np.where(
            ok_turn & np.isfinite(frac), (dist_turn / 1000.0) * frac, np.nan)

    for col in out.columns:
        out[col] = out[col].replace([np.inf, -np.inf], np.nan)
    return out


def build_model_dataset_v2(force: bool = False) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_dataset = OUT_DIR / "model_dataset_v2.0.parquet"
    if out_dataset.exists() and not force:
        raise FileExistsError(f"{out_dataset} exists; use --force to regenerate")

    dataset = pd.read_parquet(V1_2_DATASET)
    v12_manifest = json.loads(V1_2_MANIFEST.read_text(encoding="utf-8"))
    exposure = pd.read_parquet(EXPOSURE_PATH)

    if len(dataset) != len(exposure):
        raise RuntimeError(f"row mismatch: v1.2 {len(dataset)} vs exposure {len(exposure)}")
    merged = exposure[["operational_exposure_id"] + EXPOSURE_COLUMNS].merge(
        dataset, on="operational_exposure_id", how="left", validate="one_to_one",
        suffixes=("", "_dup"))
    dup = [c for c in merged.columns if c.endswith("_dup")]
    if dup:
        raise RuntimeError(f"overlapping columns between exposure and v1.2: {dup}")

    phys = _physics_features(dataset, exposure)
    new_cols = EXPOSURE_COLUMNS + [c for c in phys.columns]
    out = pd.concat([dataset, merged[EXPOSURE_COLUMNS], phys], axis=1)

    # Gate: original X block must remain fully populated (as in v1.2). New columns
    # have EXPECTED missingness, recorded in the manifest.
    roles = dict(v12_manifest["column_roles"])
    orig_x = [c for c, r in roles.items() if r == "feature"]
    na_cells = int(out[orig_x].isna().sum().sum())
    if na_cells != 0:
        raise RuntimeError(f"original X block has {na_cells} NA cells (should be 0)")
    for c in new_cols:
        if c in roles:
            raise RuntimeError(f"new column collides with existing role: {c}")
        roles[c] = "feature"

    missing = {c: float(out[c].isna().mean()) for c in new_cols}
    constants = [c for c in orig_x + new_cols if out[c].nunique(dropna=True) <= 1]
    if constants:
        raise RuntimeError(f"constant X columns: {constants}")

    out_manifest = dict(v12_manifest)
    out_manifest["dataset_version"] = DATASET_VERSION
    out_manifest["parent_dataset_version"] = PARENT_VERSION
    out_manifest["column_roles"] = roles
    out_manifest["phase2"] = {
        "workstream_1_exposure": EXPOSURE_COLUMNS,
        "workstream_3_physics": [c for c in phys.columns],
        "weather_exposure_index": "NOT materialised (PENDING, no provider; blocked-value rule)",
        "expected_missing_pct": {k: round(v * 100, 2) for k, v in missing.items()},
    }
    out_manifest["input_sha256"] = {
        "parent_dataset_v1.2": _sha256(V1_2_DATASET),
        "exposure_features_v2": _sha256(EXPOSURE_PATH),
    }
    out_manifest["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    out_manifest["split_rows"] = {name: int((out["split"] == name).sum()) for name in ("train", "val", "test")}
    out_manifest["rows"] = int(len(out))

    out.to_parquet(out_dataset, index=False)
    (OUT_DIR / "model_dataset_manifest_v2.0.json").write_text(
        json.dumps(out_manifest, indent=2) + "\n", encoding="utf-8")
    for name in ("train", "val", "test"):
        out[out["split"] == name].to_parquet(OUT_DIR / f"{name}_v2.0.parquet", index=False)

    _write_card(out_manifest, missing)
    _write_data_additions(v12_manifest, missing)
    _write_changelog(missing)

    print(f"v2.0 dataset written: {out_dataset.relative_to(PROJECT_ROOT)}  rows={len(out):,}")
    for col, pct in sorted(missing.items(), key=lambda kv: -kv[1]):
        print(f"  {col:44s} missing {pct*100:6.2f}%")
    return {"dataset": out_dataset,
            "manifest": OUT_DIR / "model_dataset_manifest_v2.0.json",
            "card": OUT_DIR / "dataset_card_v2.0.md"}


def _write_card(manifest: dict, missing: dict) -> None:
    lines = [
        f"# Dataset Card — model dataset {DATASET_VERSION}",
        "",
        f"- **Parent:** {PARENT_VERSION} (immutable; 96-feature X block + split + labels identical for retained rows)",
        f"- **Rows (supervised):** {manifest['rows']:,}",
        f"- **Added columns:** {len(missing)} (WS1 exposure + WS3 physics)",
        f"- **Label spec:** {manifest['label_spec_version']} (unchanged from v1.2)",
        f"- **Split rows:** train={manifest['split_rows']['train']:,} · val={manifest['split_rows']['val']:,} · test={manifest['split_rows']['test']:,}",
        f"- Generated: {manifest['generated_at_utc']}",
        "",
        "## Phase-2 additions",
        "",
        "| column | expected missing % |",
        "| --- | ---: |",
    ]
    for col, pct in sorted(missing.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {col} | {pct*100:.1f} |")
    lines += [
        "",
        "## Governance",
        "",
        "- Distance features use the owner-APPROVED safe daily aggregation (2026-08-05).",
        "- `interval_distance_km_experimental` remains un-renamed/untouched.",
        "- Wear-derived columns are EXPERIMENTAL (engineering wear definition not yet signed off).",
        "- `weather_exposure_index` is NOT materialised (PENDING, no provider).",
    ]
    (OUT_DIR / "dataset_card_v2.0.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_data_additions(parent_manifest: dict, missing: dict) -> None:
    additions = {
        "metadata_file_version": "1.0.0",
        "purpose": "Reconstruction record: what data was added to the model dataset, when, from what inputs.",
        "dataset_version": DATASET_VERSION,
        "parent_dataset_version": PARENT_VERSION,
        "added_at_utc": datetime.now(timezone.utc).isoformat(),
        "builders": {
            "exposure": "model_datasets/build_exposure_features_v2.py",
            "dataset": "model_datasets/build_model_dataset_v2.py",
            "parent_builder": "model_datasets/build_model_dataset_v1_2.py",
        },
        "inputs": {
            "v1.2_dataset": {"path": str(V1_2_DATASET.relative_to(PROJECT_ROOT)), "sha256": _sha256(V1_2_DATASET)},
            "exposure_features_v2": {"path": str(EXPOSURE_PATH.relative_to(PROJECT_ROOT)), "sha256": _sha256(EXPOSURE_PATH)},
            "rtis_daily_safe": {"path": "distance_recovery/data/processed/rtis_daily_safe.parquet"},
            "wheel_measurements": {"path": "data/silver/wheel_measurements.parquet"},
            "fois_transitions": {"path": "distance_recovery/data/processed/fois_transition_distances.parquet"},
        },
        "reconstruct_commands": [
            ".ayush\\Scripts\\python.exe model_datasets\\build_exposure_features_v2.py --force",
            ".ayush\\Scripts\\python.exe model_datasets\\build_model_dataset_v2.py --force",
        ],
        "columns": {col: {"workstream": "WS1 Exposure", "status": "READY_FOR_MATERIALISATION",
                          "expected_missing_pct": round(missing[col] * 100, 2)}
                    for col in [
                        "interval_distance_km", "distance_per_day_km",
                        "distance_since_last_inspection_km", "running_days", "running_days_pct",
                        "rtis_distance_coverage_days_in_interval", "rtis_distance_coverage_pct_in_interval",
                    ]},
    }
    additions["columns"].update({
        col: {"workstream": "WS1 Exposure", "status": "READY_WITH_CAVEAT",
              "expected_missing_pct": round(missing[col] * 100, 2)}
        for col in ["running_hours_proxy", "maintenance_density_per_day",
                    "maintenance_density_per_1000km", "distance_since_turning_km"]
    })
    additions["columns"].update({
        col: {"workstream": "WS3 Physics", "status": "EXPERIMENTAL (pending engineering wear sign-off)",
              "expected_missing_pct": round(missing[col] * 100, 2)}
        for col in missing if col.startswith(("wear_per_1000km", "remaining_material_per_km",
                                              "projected_remaining_km", "exposure_index"))
    })
    additions["not_materialised"] = {
        "weather_exposure_index": "PENDING - no weather provider/archive exists",
        "track_curve_severity_index": "FUTURE - track geometry deferred (WS5)",
    }
    (OUT_DIR / "DATA_ADDITIONS.json").write_text(json.dumps(additions, indent=2) + "\n", encoding="utf-8")


def _write_changelog(missing: dict) -> None:
    lines = [
        "# Model dataset change log (Phase 2)",
        "",
        f"## {DATASET_VERSION} — {datetime.now(timezone.utc).date().isoformat()}",
        "",
        "### Workstream 1 — Operational Exposure (added)",
        "- `interval_distance_km`, `distance_per_day_km`, `distance_since_last_inspection_km`, "
        "`running_days`, `running_days_pct` — from the **owner-APPROVED** RTIS safe daily "
        "ledger (07_safe_rtis_daily_aggregation.py, signed off 2026-08-05).",
        "- `rtis_distance_coverage_days/pct_in_interval` — reporting-day coverage of the sum.",
        "- `running_hours_proxy` — FOIS active-movement time (bounded gaps); low coverage "
        "(FOIS window 2025-10 -> 2026-06).",
        "- `maintenance_density_per_day` / `maintenance_density_per_1000km` — job cards per "
        "day / per 1000 km.",
        "- `distance_since_turning_km` — cumulative approved km since last wsmturning=1 "
        "(per wheelset equipment; NULL if none in history).",
        "",
        "### Workstream 3 — Physics-informed (added)",
        "- `wear_per_1000km_s1/s2` — clean-interval material loss per 1000 km (no turning at "
        "interval end). EXPERIMENTAL: engineering wear definition pending sign-off.",
        "- `remaining_material_per_km_s1/s2` — remaining material per km run since turning.",
        "- `projected_remaining_km_s1/s2` — remaining material / wear-per-km lifetime estimate.",
        "- `exposure_index_s1/s2` — distance-since-turning (1000 km) x material-consumed fraction.",
        "",
        "### Not materialised",
        "- `weather_exposure_index` — PENDING (no provider).",
        "- Track curve severity — FUTURE (WS5 deferred).",
        "",
        "### Governance notes",
        "- `interval_distance_km_experimental` left un-renamed/untouched.",
        "- v1.2 96-feature X block byte-identical; splits and labels unchanged.",
        "",
        "### Reconstruction",
        "```powershell",
        ".ayush\\Scripts\\python.exe model_datasets\\build_exposure_features_v2.py --force",
        ".ayush\\Scripts\\python.exe model_datasets\\build_model_dataset_v2.py --force",
        "```",
    ]
    (OUT_DIR / "CHANGELOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name, path in build_model_dataset_v2(force=args.force).items():
        print(f"{name}: {path.relative_to(PROJECT_ROOT)}")
