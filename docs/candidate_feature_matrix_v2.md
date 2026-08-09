# Candidate Feature Matrix v2.0 — WAP7 wheel-health feature build-out

> Reconstructed from the validated source audit (`validation/candidate_source_validation.md`)
> and the live-DB schema scans of 2026-08-03. Each candidate is mapped to its source,
> measured availability, and build status. **This matrix is the plan for materialising
> all 26 features as well as the data allows.**

**Cohort:** WAP7 **type** (`LomType = 9`, resolved via `LotTypeName='WAP7'`) = **2,317 locos**.
**Grain:** one Gold-B inspection interval, keyed by `operational_exposure_id`.
**Governance:** blocked features must NOT be materialised as numeric estimates. See
`configs/engineering_feature_specification_v1.json`.

---

## A. Behaviour — measurement state & change (from `WheelSetMeasurements`)

| # | Feature | Source fields | Availability | Status |
| --- | --- | --- | --- | --- |
| 1 | Interval duration (days) | `interval_start/end_timestamp` | 225,262 intervals | ✅ RELEASED |
| 2 | Raw endpoint diameter change | `wsmDia1/wsmDia2` endpoint diff | 100% both sides | ✅ RELEASED (caveat) |
| 3 | Flange-thickness endpoint change | `wsmFlangeThickness1/2` | 99.99% | 🟢 buildable |
| 4 | Root-wear endpoint change | `wsmRoot1/2` | ✅ semantics resolved (Q8: direct defect depth, 3 mm max, lower better) | 🟢 buildable |
| 5 | Wheel-gauge endpoint change | `wsmWheelGauge1/2` | present | 🟢 buildable |
| 6 | Tire-thickness / thread change | `wsmTireThikness1/2`, `wsmThread1/2` | ✅ tread resolved (Q8: defect depth, 3 mm max, lower better); tire-thickness unit caveat | 🟢 buildable |
| 7 | Skid-turn source flag | `wsmSkidTurn1/2` | ~2% flagged | 🟢 buildable (caveat) |
| 8 | Measurement analysis flag | `wsmWheelAnalysisFlag` | 0/1/2 | 🟢 buildable (metadata) |
| 9 | Prior-measurement diff fields | `wsmPrvDia1/2`, `wsmDateDiff` | present | 🟢 buildable (metadata) |

## B. Identity — wheel position & timeline quality

| # | Feature | Source fields | Availability | Status |
| --- | --- | --- | --- | --- |
| 10 | Assignment quality tier | Business Truth v1.0 | 225,262 Gold B | ✅ RELEASED |
| 11 | Wheel position (1–12) | `WheelFormationTemplates` × `(wsmWheelSetPosition, wsmW1EndType)` | 98.9% mappable | 🟢 buildable |
| 12 | Axle position (1–6) | `wsmWheelSetPosition` | 98.9% | 🟢 buildable |
| 13 | Inspection count (per wheelset) | count of WSM rows per `wsmEquipmentId` (NOT `wsmWRId`) | §7.7: re-keyed count is sane (median 7/wheelset) | 🟢 buildable on `wsmEquipmentId` |

## C. Maintenance — turning, schedule, abnormal events

| # | Feature | Source fields | Availability | Status |
| --- | --- | --- | --- | --- |
| 14 | Turning indicator (raw) | `wsmturning1/2` | ~2% (99.99% fill in store) | ✅ RELEASED (caveat; Q1/Q3 confirmed) |
| 15 | Days since turning | `wsmturning` events only (NOT `LwrTurningType` — it is a post-turning inspection outcome per Q3; 92.5% un-flagged) | 41,517 intervals (18.4%) | ✅ RELEASED (caveat; Q1/Q2 confirmed, minor flag undercount) |
| 16 | Wheel profile (QR) | `LwrWheelProfile` (1/2) | 75% fill; join `wsmWRId=LwrId` matches 99.98% on WAP7 intervals (§7.7 resolved) | 🟢 buildable (2-class) |
| 17 | Previous maintenance / schedule | `LwrScheduleId` (28 types), `LocoHistory` | 97.6% fill; same join (§7.7 resolved) | 🟢 buildable |
| 18 | Job-card creation count | `SectionJobcards.SejId` | 161,551 intervals | ✅ RELEASED (caveat) |
| 19 | Abnormal event count | `AbnormalityRegister` | 81,181 WAP7 rows | 🟢 buildable |
| 20 | Equipment-failure count | `EquipmentFailureRegister` via LECR | 7,381 WAP7 rows | 🟢 buildable |
| 21 | Wheel age proxy | `EquipmentMasterRegister.EmrDoR` → `EmrDoM` → `wsmProvDate` cascade | 178,243 intervals (79.1%); source col `wheel_age_date_source` | ✅ RELEASED (caveat; Q6) |

## D. Exposure — route, shed, load, reporting

| # | Feature | Source fields | Availability | Status |
| --- | --- | --- | --- | --- |
| 22 | Static axle-load configuration | `LocoTypes.LotAxelLoad` | WAP7 = 20.5 | ✅ RELEASED (unit caveat) |
| 23 | Home shed | `DailyOverdueLocoCount.HomeShed` | 246,751 rows / 0% null | 🟢 buildable |
| 24 | Zone / Division | `OnlineDefects_LogHistory` | 106,300 rows; 99.5/99.9% fill | 🟢 buildable |
| 25 | RTIS source-event count | `rtis_emergency.IrledId` | 2,234 intervals | ✅ RELEASED (caveat) |
| 26 | RTIS reporting coverage | `rtis_mileage` dates | 134,866 intervals | ✅ RELEASED (caveat) |

## E. Deliberately blocked (must NOT be materialised)

| Feature | Block reason |
| --- | --- |
| Wear rate (mm/day) | No approved wear definition / turning reset rule |
| Wear rate (mm/km) | No released distance |
| Interval distance (km) | RTIS distance semantics unresolved |
| Weather exposure index | No provider / validated location-time coverage |
| Curve / gradient severity | No track-geometry source |
| Wheel health index | Depends on released degradation + approved limits |
| RUL / prediction | Needs released labels + censoring policy |

---

## Build priorities (next execution order)

1. **B11–B13 + C16–C17 + D23–D24** — wheel position, axle position, inspection count (keyed on
   `wsmEquipmentId`), **wheel profile, schedule** (join `wsmWRId=LwrId` confirmed 99.98% on
   WAP7 intervals, §7.7), home shed, zone/division — all buildable. `wsmEquipmentId` = `EmrId`
   is the stable per-wheelset identity; `wsmWRId` is the per-measurement register reference.
2. **C14–C15 (turning) — RELEASED (Q1/Q2/Q3 confirmed):** `turning_indicator_raw` =
   endpoint `wsmturning1` (99.99% fill); `days_since_turning` per-equipment (18.4% of intervals,
   median 282 d). `LwrTurningType` is a post-turning inspection outcome (Q3), never an event.
3. **C21 (wheel age) — RELEASED (Q6):** EmrDoR-anchored cascade (EmrDoR→EmrDoM→wsmProvDate)
   with `wheel_age_date_source`; negatives excluded by the at-or-before-interval-end rule.
4. **C19–C20 (abnormal/failure events)** — needs event-code mapping at join time.
5. **A3–A9 (geometry deltas)** — add after the measurement-unit/sign decision for each field.
   **A4/A6 (root/tread) unblocked (Q8, 2026-08-08):** direct defect depth, 3 mm max, lower-is-better;
   compute endpoint deltas and `margin = 3.0 - value` (negative = beyond condemning).

## Immediate confirmation needed from the user

- Confirm the 26-feature list matches this matrix (add/remove candidates before I
  materialise the Feature Store v2 columns).
- Confirm the feature-store route: extend `engineering_feature_specification_v1.json`
  (statuses + materialization mappings) so the existing builder materialises them, rather
  than writing a separate v2 builder.
