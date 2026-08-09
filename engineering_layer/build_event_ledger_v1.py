"""Build the Engineering Event Ledger v1.0 (Phase 3C Stage A).

Detects lifecycle / maintenance events from Silver wheel measurements using the
trajectory-driven rules in configs/engineering_event_ledger_spec_v1.json:

- Trajectory-driven: classification follows the diameter path (does an upward
  change persist or revert?), NOT the presence of metadata flags.
- delta <= +3 mm (including all downward wear) is normal within-segment
  wear / measurement variation and NEVER emits an event, even when
  wsmWheelAnalysisFlag==2 or wsmProvDate changes.
- Upward bands:
  * ambiguous +3..+10 mm: persists >= 2 -> UNKNOWN; reverts -> ANOMALY
  * strong > +10 mm: persists + >=1 corroborator -> CONFIRMED;
    persists, no corroborator -> LIKELY; reverts -> ANOMALY; unverified -> UNKNOWN
- Corroborators (any of): analysis_flag_2, provision_change, near_new_wheel_diameter
  (post-jump diameter within +-10 mm of the locomotive type's LotWheelDiaNew —
  no global new-wheel constant).
- turning: wsmturning1 == 1 (owner-confirmed recorded event).

UNKNOWN is quarantined evidence: a potential lifecycle boundary that cannot be
confidently resolved. It is retained (is_lifecycle_boundary=false), never forced
into a boundary, and its population is quantified for review.

Events are deduplicated to one record per (position_id, event_date) with event
priority replacement > turning > anomaly > unknown.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "data" / "silver" / "wheel_measurements.parquet"
TIMELINE = ROOT / "data" / "gold" / "business_truth" / "v1.0" / "wheel_timeline_gold_b.parquet"
LOCO_TYPES = ROOT / "data" / "bronze" / "loco_types.parquet"
SPEC = ROOT / "configs" / "engineering_event_ledger_spec_v1.json"
OUTPUT_DIR = ROOT / "data" / "gold" / "engineering_event_ledger" / "v1.0"
OUTPUT = OUTPUT_DIR / "engineering_event_ledger.parquet"
EVIDENCE_OUTPUT = OUTPUT_DIR / "engineering_event_ledger_evidence.parquet"
UNKNOWN_BREAKDOWN_OUTPUT = OUTPUT_DIR / "engineering_event_ledger_unknown_breakdown.json"
MANIFEST = OUTPUT_DIR / "engineering_event_ledger_manifest_v1.0.json"
CARD = OUTPUT_DIR / "engineering_event_ledger_card_v1.0.md"

DIAMETER_WINDOW = (1000.0, 1100.0)
JUMP_THRESHOLD_MM = 10.0
VARIATION_FLOOR_MM = 3.0
PERSISTENCE_BAND_MM = 5.0
MIN_PERSISTENCE = 2
NEAR_NEW_BAND_MM = 10.0
SCORE_MAP = {"CONFIRMED": 0.99, "LIKELY": 0.8, "RECORDED": 1.0, "ANOMALY": 0.35, "UNKNOWN": 0.15}
_PRIORITY = {"replacement": 0, "turning": 1, "anomaly": 2, "unknown": 3}

_EVENT_COLUMNS = ["position_id", "event_date", "event_type", "confidence", "old_dia", "new_dia", "persistence", "signals", "is_lifecycle_boundary", "source_record_id"]
_EVIDENCE_COLUMNS = ["position_id", "event_date", "source_record_id", "old_dia", "new_dia", "delta_mm", "analysis_flag_raw", "prov_date_raw", "prev_prov_date_raw", "flag2", "prov_change", "turning", "jump", "emitted_event", "event_type", "confidence"]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _side_diameter(d1: pd.Series, d2: pd.Series) -> pd.Series:
    one = pd.to_numeric(d1, errors="coerce").where(d1.between(*DIAMETER_WINDOW))
    two = pd.to_numeric(d2, errors="coerce").where(d2.between(*DIAMETER_WINDOW))
    return one.combine_first(two)


def _dia(value: float) -> float:
    return float(value) if np.isfinite(value) else float("nan")


def _corroborators(flag2: bool, prov_change: bool) -> list[str]:
    return [signal for signal, fired in (("analysis_flag_2", flag2), ("provision_change", prov_change)) if fired]


def _scan_forward(dia: np.ndarray, jump_idx: int, old: float, new: float) -> tuple[int, bool]:
    persistence = 0
    first_next = float("nan")
    for k in range(jump_idx + 1, len(dia)):
        if np.isfinite(dia[k]):
            first_next = dia[k]
            if abs(dia[k] - new) <= PERSISTENCE_BAND_MM:
                persistence += 1
            else:
                break
        else:
            break
    reverts = np.isfinite(first_next) and abs(first_next - old) <= PERSISTENCE_BAND_MM
    return persistence, reverts


def _scan_sequential_replacement(dia: np.ndarray, jump_idx: int, old: float, new: float, new_wheel_ref: float) -> bool:
    """Two-level persistence: a second upward transition within the next few
    inspections lands at or near the locomotive type's new-wheel diameter.

    Covers sequences like 1033 -> 1069 -> 1091 (WAP7 new wheel 1092): the first
    jump does NOT itself land near the new-wheel diameter and is not stable, but
    the trajectory approaches the near-new state shortly after — a pattern a
    single-level persistence rule cannot confirm. A jump that already lands
    near-new is NOT this class (it is a direct-jump persistence case).
    """
    if not np.isfinite(new_wheel_ref):
        return False
    if abs(new - new_wheel_ref) <= NEAR_NEW_BAND_MM:
        return False
    lookahead = 3
    for k in range(jump_idx + 1, min(jump_idx + 1 + lookahead, len(dia))):
        if not np.isfinite(dia[k]):
            continue
        if abs(dia[k] - new_wheel_ref) <= NEAR_NEW_BAND_MM:
            return True
    return False


def detect_events(measurements: pd.DataFrame, near_new_lookup: pd.Series | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run trajectory-driven detection. near_new_lookup maps position_id -> LotWheelDiaNew."""
    m = measurements.copy()
    m = m.dropna(subset=["wheelset_equipment_id", "measurement_timestamp"])
    m["position_id"] = m["wheelset_equipment_id"].astype("int64")
    m = m.sort_values(["position_id", "measurement_timestamp"]).reset_index(drop=True)
    m["dia"] = _side_diameter(m["wsmDia1"], m["wsmDia2"])
    m["prev_dia"] = m.groupby("position_id")["dia"].shift(1)
    m["flag2"] = pd.to_numeric(m["wsmWheelAnalysisFlag"], errors="coerce").eq(2)
    prov = pd.to_datetime(m["wsmProvDate"], errors="coerce")
    m["prev_prov"] = prov.groupby(m["position_id"]).shift(1)
    m["prov_change"] = prov.notna() & m["prev_prov"].notna() & (prov != m["prev_prov"])
    m["turning"] = pd.to_numeric(m["wsmturning1"], errors="coerce").fillna(0).eq(1)

    events: list[tuple] = []
    evidence: list[tuple] = []
    for position, group in m.groupby("position_id", sort=False):
        dia = group["dia"].to_numpy()
        flag2 = group["flag2"].to_numpy()
        prov_change = group["prov_change"].to_numpy()
        turning = group["turning"].to_numpy()
        stamps = group["measurement_timestamp"].to_numpy()
        record_ids = group["measurement_record_id"].astype(str).to_numpy()
        flag_raw = group["wsmWheelAnalysisFlag"].to_numpy()
        prov_raw = prov.loc[group.index].to_numpy()
        prev_prov_raw = group["prev_prov"].to_numpy()
        new_wheel_ref = float(near_new_lookup.get(position, np.nan)) if near_new_lookup is not None else float("nan")
        n = len(group)
        for i in range(1, n):
            old = dia[i - 1]
            new = dia[i]
            has_dia = np.isfinite(old) and np.isfinite(new)
            delta = new - old if has_dia else float("nan")

            row = (
                position, stamps[i], record_ids[i], _dia(old), _dia(new), float(delta) if np.isfinite(delta) else float("nan"),
                float(flag_raw[i]) if np.isfinite(flag_raw[i]) else float("nan"),
                prov_raw[i] if not pd.isna(prov_raw[i]) else None, prev_prov_raw[i] if not pd.isna(prev_prov_raw[i]) else None,
                bool(flag2[i]), bool(prov_change[i]), bool(turning[i]), bool(has_dia and delta > VARIATION_FLOOR_MM),
            )
            if turning[i]:
                events.append((position, stamps[i], "turning", "RECORDED", _dia(old), _dia(new), 1, ["owner_recorded_turning_flag"], True, record_ids[i]))
                evidence.append(row + (True, "turning", "RECORDED"))
                continue
            if not has_dia:
                if flag2[i] or prov_change[i]:
                    evidence.append(row + (False, None, None))
                continue
            # delta <= variation floor: normal wear / measurement variation, no event.
            if delta <= VARIATION_FLOOR_MM:
                if flag2[i] or prov_change[i] or turning[i]:
                    evidence.append(row + (False, None, None))
                continue

            persistence, reverts = _scan_forward(dia, i, old, new)
            if delta > JUMP_THRESHOLD_MM:
                signals = _corroborators(flag2[i], prov_change[i])
                if np.isfinite(new_wheel_ref) and abs(new - new_wheel_ref) <= NEAR_NEW_BAND_MM:
                    signals.append("near_new_wheel_diameter")
                if reverts:
                    events.append((position, stamps[i], "anomaly", "ANOMALY", old, new, persistence, ["transient_jump"], False, record_ids[i]))
                    evidence.append(row + (True, "anomaly", "ANOMALY"))
                elif persistence >= MIN_PERSISTENCE and signals:
                    events.append((position, stamps[i], "replacement", "CONFIRMED", old, new, persistence, ["persistent_jump", *signals], True, record_ids[i]))
                    evidence.append(row + (True, "replacement", "CONFIRMED"))
                elif persistence >= MIN_PERSISTENCE:
                    events.append((position, stamps[i], "replacement", "LIKELY", old, new, persistence, ["persistent_jump"], True, record_ids[i]))
                    evidence.append(row + (True, "replacement", "LIKELY"))
                elif _scan_sequential_replacement(dia, i, old, new, new_wheel_ref):
                    events.append((position, stamps[i], "unknown", "UNKNOWN", old, new, persistence, ["sequential_replacement"], False, record_ids[i]))
                    evidence.append(row + (True, "unknown", "UNKNOWN"))
                else:
                    events.append((position, stamps[i], "unknown", "UNKNOWN", old, new, persistence, ["unverified_jump"], False, record_ids[i]))
                    evidence.append(row + (True, "unknown", "UNKNOWN"))
            else:
                # ambiguous upward +3..+10 mm
                if reverts:
                    events.append((position, stamps[i], "anomaly", "ANOMALY", old, new, persistence, ["transient_jump"], False, record_ids[i]))
                    evidence.append(row + (True, "anomaly", "ANOMALY"))
                elif persistence >= MIN_PERSISTENCE:
                    events.append((position, stamps[i], "unknown", "UNKNOWN", old, new, persistence, ["ambiguous_upward_persist"], False, record_ids[i]))
                    evidence.append(row + (True, "unknown", "UNKNOWN"))
                else:
                    events.append((position, stamps[i], "unknown", "UNKNOWN", old, new, persistence, ["ambiguous_upward_unverified"], False, record_ids[i]))
                    evidence.append(row + (True, "unknown", "UNKNOWN"))

    events_df = pd.DataFrame(events, columns=_EVENT_COLUMNS) if events else pd.DataFrame(columns=_EVENT_COLUMNS)
    evidence_df = pd.DataFrame(evidence, columns=_EVIDENCE_COLUMNS) if evidence else pd.DataFrame(columns=_EVIDENCE_COLUMNS)
    if len(events_df):
        events_df["confidence_score"] = events_df["confidence"].map(SCORE_MAP)
        events_df["_priority"] = events_df["event_type"].map(_PRIORITY)
        events_df["_day"] = pd.to_datetime(events_df["event_date"]).dt.normalize()
        events_df = events_df.sort_values(["position_id", "_day", "_priority"], kind="stable")
        events_df = events_df.drop_duplicates(subset=["position_id", "_day"], keep="first").drop(columns=["_priority", "_day"]).reset_index(drop=True)
    if len(evidence_df):
        evidence_df["emitted_event"] = evidence_df["emitted_event"].astype(bool)
        evidence_df["flag2"] = evidence_df["flag2"].astype(bool)
        evidence_df["prov_change"] = evidence_df["prov_change"].astype(bool)
        evidence_df["turning"] = evidence_df["turning"].astype(bool)
        evidence_df["jump"] = evidence_df["jump"].astype(bool)
        evidence_df["event_type"] = evidence_df["event_type"].astype("string")
        evidence_df["confidence"] = evidence_df["confidence"].astype("string")
    return events_df, evidence_df


def unknown_breakdown(ledger: pd.DataFrame) -> dict:
    """Quantify the UNKNOWN population for review (what does it consist of?)."""
    u = ledger[ledger["event_type"].eq("unknown")].copy()
    u["year"] = pd.to_datetime(u["event_date"]).dt.year
    u["abs_delta"] = (u["new_dia"] - u["old_dia"]).abs()

    def sig_group(signals):
        if not isinstance(signals, list):
            return "unverified_jump"
        if "unverified_jump" in signals:
            return "unverified_jump"
        if "sequential_replacement" in signals:
            return "sequential_replacement"
        if "ambiguous_upward_persist" in signals:
            return "ambiguous_upward_persist"
        if "ambiguous_upward_unverified" in signals:
            return "ambiguous_upward_unverified"
        return "other"

    u["sig"] = u["signals"].map(sig_group)
    bins = [0, 3, 5, 10, 15, 20, 30, 1e9]
    labels = ["0-3", "3-5", "5-10", "10-15", "15-20", "20-30", "30+"]
    u["delta_bin"] = pd.cut(u["abs_delta"], bins=bins, labels=labels, right=False)
    total = len(u)
    return {
        "total_unknown": int(total),
        "pct_of_all_events": round(100.0 * total / max(1, len(ledger)), 2),
        "by_signal": u["sig"].value_counts().astype(int).to_dict(),
        "by_delta_bin": u["delta_bin"].value_counts().astype(int).to_dict(),
        "by_year": u["year"].value_counts().sort_index().astype(int).to_dict(),
        "meaningful_candidates": int(u["abs_delta"].gt(JUMP_THRESHOLD_MM).sum()),
        "meaningful_candidates_pct_of_unknown": round(100.0 * u["abs_delta"].gt(JUMP_THRESHOLD_MM).mean(), 2) if total else 0.0,
        "by_loco_type": {},  # filled in main() where LocoType is resolved
    }


def replacement_before_horizon(ledger: pd.DataFrame, measurement_time: pd.Timestamp, horizon_days: int) -> bool:
    """Capability: True if a lifecycle-boundary replacement falls within (t, t+H].

    Pure point-in-time: only events with event_date > t are considered.
    """
    t = pd.Timestamp(measurement_time)
    horizon_end = t + pd.Timedelta(days=horizon_days)
    replacement = ledger[ledger["event_type"].eq("replacement")]
    return bool(((replacement["event_date"] > t) & (replacement["event_date"] <= horizon_end)).any())


def main() -> None:
    if any(path.exists() for path in (OUTPUT, EVIDENCE_OUTPUT, MANIFEST, CARD)):
        raise FileExistsError("Engineering Event Ledger v1.0 already exists; create a new version instead of overwriting it.")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    columns = ["wheelset_equipment_id", "measurement_timestamp", "measurement_record_id", "wsmDia1", "wsmDia2", "wsmWheelAnalysisFlag", "wsmProvDate", "wsmturning1"]
    measurements = pd.read_parquet(SILVER, columns=columns)
    timeline_columns = ["measurement_record_id", "locomotive_id", "LocoType", "wheelset_equipment_id"]
    timeline = pd.read_parquet(TIMELINE, columns=timeline_columns).dropna(subset=["measurement_record_id"])
    timeline["measurement_record_id"] = timeline["measurement_record_id"].astype(str)
    timeline = timeline.drop_duplicates(subset=["measurement_record_id"])

    # Per-type new-wheel diameter reference (no global constant).
    loco_types = pd.read_parquet(LOCO_TYPES, columns=["LotTypeName", "LotWheelDiaNew"]).dropna(subset=["LotWheelDiaNew"])
    type_ref = dict(zip(loco_types["LotTypeName"], loco_types["LotWheelDiaNew"]))
    timeline["_new_wheel_dia"] = timeline["LocoType"].map(type_ref)
    near_new_lookup = timeline.dropna(subset=["wheelset_equipment_id", "_new_wheel_dia"]).drop_duplicates(subset=["wheelset_equipment_id"]).set_index("wheelset_equipment_id")["_new_wheel_dia"]

    ledger, evidence = detect_events(measurements, near_new_lookup=near_new_lookup)
    ledger = ledger.merge(timeline.rename(columns={"measurement_record_id": "source_record_id", "locomotive_id": "loco_id", "LocoType": "loco_type"}),
                          how="left", on="source_record_id", validate="many_to_one")
    ledger = ledger.drop(columns=["source_record_id"])
    ledger = ledger.sort_values(["position_id", "event_date"]).reset_index(drop=True)
    ledger["is_lifecycle_boundary"] = ledger["is_lifecycle_boundary"].astype(bool)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(OUTPUT, index=False)
    evidence.to_parquet(EVIDENCE_OUTPUT, index=False)

    breakdown = unknown_breakdown(ledger)
    if "loco_type" in ledger.columns:
        ut = ledger[ledger["event_type"].eq("unknown")]
        breakdown["by_loco_type"] = ut["loco_type"].value_counts().astype(int).to_dict()
    UNKNOWN_BREAKDOWN_OUTPUT.write_text(json.dumps(breakdown, indent=2, default=str) + "\n", encoding="utf-8")

    counts = ledger.groupby(["event_type", "confidence"]).size().to_dict()
    evidence_emitted = int(evidence["emitted_event"].sum())
    manifest = {
        "dataset_version": "engineering_event_ledger_v1.0",
        "specification_id": spec["specification_id"],
        "specification_version": spec["specification_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "grain": "one detected lifecycle / maintenance event per (position_id, event_date)",
        "rows": int(len(ledger)),
        "columns": int(len(ledger.columns)),
        "trajectory_driven": True,
        "variation_floor_mm": VARIATION_FLOOR_MM,
        "near_new_band_mm": NEAR_NEW_BAND_MM,
        "input_sha256": {"silver_wheel_measurements": checksum(SILVER), "timeline_gold_b": checksum(TIMELINE), "loco_types": checksum(LOCO_TYPES), "spec": checksum(SPEC)},
        "event_counts": {f"{k[0]}::{k[1]}": int(v) for k, v in counts.items()},
        "lifecycle_boundary_events": int(ledger["is_lifecycle_boundary"].sum()),
        "evidence_rows": int(len(evidence)),
        "evidence_emitted_events": evidence_emitted,
        "evidence_normal_wear_or_variation": int(len(evidence) - evidence_emitted),
        "loco_id_resolved_rows": int(ledger["loco_id"].notna().sum()),
        "semantics": "Trajectory-driven lifecycle/maintenance events; delta <= +3 mm never emits an event; UNKNOWN is quarantined unresolved evidence; near-new-wheel corroboration derived from LotWheelDiaNew per loco type.",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Engineering Event Ledger v1.0", "",
        f"- **Rows:** {len(ledger):,}",
        f"- **Grain:** one event per (position_id, event_date); event priority replacement > turning > anomaly > unknown.",
        "- **Taxonomy:** replacement (CONFIRMED/LIKELY boundary), turning (RECORDED boundary), anomaly (ANOMALY), unknown (UNKNOWN).",
        f"- **Trajectory-driven:** delta <= +{VARIATION_FLOOR_MM:g} mm is normal wear/variation and never emits an event (even with flag2/provision).",
        f"- **New-wheel reference:** near-new corroborator derived from LotWheelDiaNew per loco type (band +-{NEAR_NEW_BAND_MM:g} mm), no global constant.",
        f"- **UNKNOWN (quarantined evidence):** {breakdown['total_unknown']:,} unresolved transitions; see `engineering_event_ledger_unknown_breakdown.json`.",
        f"- **Evidence rows:** {len(evidence):,} signal-bearing inspections; {int(len(evidence) - evidence_emitted):,} normal-wear/variation preserved without events.",
        f"- **Lifecycle boundary events:** {int(ledger['is_lifecycle_boundary'].sum()):,}", "",
        "## Event counts", "", "| event_type | confidence | count |", "| --- | --- | ---: |",
    ]
    for (etype, conf), count in sorted(counts.items()):
        lines.append(f"| {etype} | {conf} | {count:,} |")
    lines += ["", "## Detection rules", "", "- trajectory-driven: does the upward change persist or revert?",
              "- strong jump (> +10 mm) persists + >=1 corroborator (flag2/provision/near_new) -> CONFIRMED; persists only -> LIKELY; reverts -> ANOMALY; unverified -> UNKNOWN.",
              "- ambiguous (+3..+10 mm) persists -> UNKNOWN; reverts -> ANOMALY.",
              "- delta <= +3 mm -> normal wear/variation, no event.",
              "- UNKNOWN = unresolved potential boundary, retained with is_lifecycle_boundary=false; quantified in the breakdown file."]
    CARD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
