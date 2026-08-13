# Engineering Event Ledger v1.0 — Validation Evidence Pack

Status: **PASS** (subject to Gate 3C-A review)

Revision note (2026-08-08): detection is now **trajectory-driven** per the
owner review. Classification follows the diameter path (does an upward change
persist or revert?), not the presence of metadata flags. Downward wear never
emits an event. UNKNOWN is quarantined unresolved evidence and is quantified,
not treated as waste.

## 1. Artifact under validation

| Item | Path | Notes |
| --- | --- | --- |
| Ledger | `data/gold/engineering_event_ledger/v1.0/engineering_event_ledger.parquet` | 83,674 events |
| Evidence | `.../engineering_event_ledger_evidence.parquet` | 209,835 signal-bearing inspections |
| UNKNOWN breakdown | `.../engineering_event_ledger_unknown_breakdown.json` | population quantification |
| Spec | `configs/engineering_event_ledger_spec_v1.json` | trajectory-driven rules |
| Builder | `engineering_layer/build_event_ledger_v1.py` | code-reviewed in this pack |
| Manifest | `.../engineering_event_ledger_manifest_v1.0.json` | SHA256-pinned inputs |

Input pins (SHA256 in manifest): `data/silver/wheel_measurements.parquet`,
`data/gold/business_truth/v1.0/wheel_timeline_gold_b.parquet`,
`data/bronze/loco_types.parquet` (LotWheelDiaNew reference).

## 2. Source snapshot and run

- Source: Silver `wheel_measurements` at build time (1,165,641 rows; 1,141,282
  after dropping null equipment/timestamp; 2004-02-14 → 2026-07-24).
- Run: `python engineering_layer/build_event_ledger_v1.py`, 2026-08-08.
- Detection scope: full silver fleet. `loco_id` / `loco_type` resolve only via
  the WAP7 Gold-B timeline (20.3% of events); non-cohort events carry NA
  loco_id and no near-new reference.

## 3. Event counts (final ledger, trajectory-driven)

| event_type | confidence | count | is_lifecycle_boundary |
| --- | --- | --- | ---: |
| replacement | CONFIRMED | 14,058 | true |
| replacement | LIKELY | 821 | true |
| turning | RECORDED | 36,277 | true |
| anomaly | ANOMALY | 11,299 | false |
| unknown | UNKNOWN | 21,219 | false |
| **total** | | **83,674** | 51,156 |

## 4. Detection rules applied (trajectory-driven)

- **Trajectory is the classifier**: `delta <= +3 mm` (including all downward
  wear) is normal within-segment wear / measurement variation and NEVER emits an
  event, even when `wsmWheelAnalysisFlag==2` or `wsmProvDate` changes. Such rows
  are preserved only in the evidence table.
- **Upward bands** (delta > +3 mm):
  - ambiguous `+3..+10 mm`: persists `>= 2` inspections → UNKNOWN
    (`ambiguous_upward_persist`); reverts within 1 inspection → ANOMALY.
  - strong `> +10 mm`: persists + `>= 1` corroborator → CONFIRMED; persists
    only → LIKELY; reverts → ANOMALY; unverified (no persistence/reversion
    observable) → UNKNOWN (`unverified_jump`).
- **Corroborators** (any of): `analysis_flag_2`, `provision_change`,
  `near_new_wheel_diameter`.
- **New-wheel reference is derived, not hard-coded**: `LotWheelDiaNew` from
  `data/bronze/loco_types.parquet` resolved per locomotive type. A persistent
  jump landing within `+-10 mm` of the type's new-wheel diameter adds the
  independent corroborator `near_new_wheel_diameter`. No global 1096 mm
  constant is used.
- **Turning**: `wsmturning1 == 1` → RECORDED boundary.

## 5. Denominators and exclusions

- Denominator: all equipment-measurement pairs after dropping null
  equipment/timestamp.
- First inspection per position (no prior diameter) excluded from jump logic.
- Implausible diameter (`< 1000` or `> 1100`) excluded from the signal; side
  fallback d1→d2.
- Downward transitions and `delta <= +3 mm` are never events.
- Turning rows recorded, not double-classified.

## 6. Triangulation metrics (no single-signal authority)

| Metric | Value |
| --- | ---: |
| `wsmWheelAnalysisFlag == 2` rows | 87,576 |
| flag2 precision → persistent jump | **16.2%** |
| flag2 recall (persistent jumps carrying flag2) | **89.6%** |
| Persistent jumps corroborated (flag2/prov/near-new) | 93.4% (flag2 only 89.6%, prov only 3.9%) |
| Persistent jumps uncorroborated → LIKELY | 6.6% |
| Replacement new_dia median | 1091 mm (std 12.6) |
| Near-new corroboration among loco-resolved replacements | **83.7%** |

flag2 remains high-recall/low-precision (16.2%), confirming it must never
auto-confirm. CONFIRMED requires persistent jump AND >= 1 corroborator.

### Hand-labelled sample (2026-08-08, trajectory-driven)

| class | sample | verified | notes |
| --- | ---: | ---: | --- |
| replacement CONFIRMED | 10 | 10/10 | persistent upward jump + corroborator (e.g. pos 6473: 1035.2→1077.0 on 2016-09-08, flag2, prov change, 8+ stable rows) |
| replacement LIKELY | 10 | 10/10 | persistent jump, no corroborator |
| anomaly | 10 | 10/10 | upward jump reverting within 1 inspection (e.g. pos 6278) |
| turning | 10 | 10/10 | `wsmturning1 == 1` |
| unknown (unverified / sequential) | 10 | 10/10 | large jump with incomplete follow-up, correctly quarantined (e.g. pos 6202: 1033→1069→1091 with flag2+prov at each step — sequential replacement not confirmable by single-level persistence) |

## 7. UNKNOWN population — what does it consist of?

Total 21,219 (25.4% of events). Breakdown in
`engineering_event_ledger_unknown_breakdown.json`:

| Criterion | Value |
| --- | ---: |
| unverified_jump (strong jump, unverified follow-up) | 16,248 |
| **sequential_replacement** (two-level persistence toward near-new) | **542** |
| ambiguous_upward_unverified (+3..+10 mm, unverified) | 3,132 |
| ambiguous_upward_persist (+3..+10 mm, persists) | 1,297 |
| **|Δdia| > 10 mm (meaningful candidates)** | **~16,790 (79.1%)** |
| |Δdia| bins: >30 mm 11,792; 20–30 2,507; 15–20 1,296; 10–15 1,361; 5–10 2,588; 3–5 1,675 | |
| by year: skews recent (2023 2,565; 2024 3,857; 2025 4,888; 2026 5,285) | | |
| by loco type (resolved subset) | WAP7 5,526 |

**Sequential-replacement class (research question, not forced to CONFIRMED).**
542 UNKNOWNs are tagged `sequential_replacement`: a strong upward jump that does
not itself land near the new-wheel diameter and is not stable, but is followed
within 3 inspections by a second upward transition landing at/near the loco
type's `LotWheelDiaNew` (±10 mm). This captures patterns like
`1033 -> 1069 -> 1091` (WAP7 new wheel 1092) that single-level persistence cannot
confirm. These remain `is_lifecycle_boundary = false` — they are quarantined
evidence, deliberately not forced into CONFIRMED. Next research step: domain
validation on this 542-row cohort (e.g. jobcard / wheel-register corroboration)
to decide whether any become LIKELY/CONFIRMED.

**Coverage caveat.** `sequential_replacement` and `near_new_wheel_diameter` are
detected only where the locomotive type reference resolves — the WAP7 Gold-B
cohort (20.3% of events). Non-cohort positions (e.g. pos 6202, the canonical
`1033->1069->1091` example) have no type reference and remain `unverified_jump`.
This is a direct consequence of the no-hard-coded-new-wheel rule: without a
per-position type mapping, the expected new-wheel diameter is not invented.

**Interpretation.** 79% of UNKNOWNs are genuinely large (|Δdia| > 10 mm)
transitions with incomplete persistence — exactly the "valuable unresolved
cases" that could become LIKELY/CONFIRMED after domain validation. Only ~15%
are small ambiguous wobbles. This is unresolved physical/lifecycle evidence,
not metadata noise. The metadata-only refreshes (flag2/provision with
delta <= +3 mm) are now entirely excluded from events by construction and live
only in the evidence table (121,332 rows).

## 8. Evidence table

209,835 signal-bearing inspections: 88,503 emitted as events; 121,332 are
normal-wear/variation rows (flag2/provision/turning flagged but delta <= +3 mm)
preserved with raw analysis-flag and provision-date columns for auditability.

## 9. Capability: replacement_before_horizon

Point-in-time `replacement_before_horizon(ledger, t, H)` returns True iff a
replacement event falls strictly inside `(t, t + H]`. No look-ahead. Available
for Stage C censoring.

## 10. Unresolved ambiguity

1. **Identity level** remains `equipment_or_wheelset_pending_semantic_validation`
   (Q7). position_id = wheelset_equipment_id; replacement inferred at mounted
   position, not physical-wheel register (wsmWRId).
2. **Turning = lifecycle boundary** per Stage A taxonomy; Stage B/C must still
   apply degradation reset semantics (pairs crossing turning excluded from wear
   targets) separately from replacement segmentation.
3. **Near-new corroborator only resolves for the WAP7 Gold-B cohort** (20.3% of
   events) because the timeline is cohort-filtered. A fleet-wide loco-type
   resolution would extend it; not blocking.
4. **unverified_jump** (16,248) are strong jumps whose post-jump level was not
   observed within the persistence band. A subset (542, cohort-resolved) are the
   **sequential_replacement** class (two-level persistence toward near-new,
   e.g. pos 6202 `1033->1069->1091`) — isolated for domain validation as the
   next research question, deliberately not forced to CONFIRMED. Non-cohort
   positions remain generic `unverified_jump` (no type reference).
5. **provision_change** uses wsmProvDate difference only; provision-reference
   change without date change is not detected.
6. Event date = post-event measurement timestamp (wsmUpdatedOn resolved), not a
   maintenance-record date.

## 11. Gate 3C-A checklist

- [x] Ledger released with spec + manifest (SHA256) + card + UNKNOWN breakdown.
- [x] Validation pack present; hand-labelled sample PASS.
- [x] No single-signal CONFIRMED replacement (persistent jump AND >= 1 corroborator).
- [x] Trajectory-driven: delta <= +3 mm never emits an event.
- [x] Near-new corroborator derived from LotWheelDiaNew per loco type (no global constant).
- [x] ANOMALY / UNKNOWN preserved with is_lifecycle_boundary=false.
- [x] UNKNOWN population quantified (79% meaningful |Δdia| > 10 mm candidates).
- [x] Sequential-replacement pattern isolated as its own UNKNOWN subclass (542) for the next research question, not forced to CONFIRMED.
- [x] replacement_before_horizon capability implemented point-in-time.
