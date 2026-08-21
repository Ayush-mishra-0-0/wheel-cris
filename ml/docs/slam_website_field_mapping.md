# SLAM Website Field Mapping — Provenance, Value & Bottleneck Attribution

**Date:** 2026-08-20
**Scope:** Map every column visible on the SLAM wheel-measurement website to physical
tables/columns in `SLAM_PROD_DB_10.05.2022`, state whether the pipeline extracts it today,
and give the ratio method that turns these fields into a defensible "limiting / bottleneck
wear" attribution for every historical cut (turning).

## TL;DR

1. **Every SLAM website column exists in our source DB.** The site renders one view over
   `LocoWheelRegister` + a handful of lookups (`WheelReadingPurpose`, `WheelProfile`,
   `ScheduleTypes`, `Sections`, `FunctionalLocations`, `Employees`).
2. **The decisive field — "Reason Of Turning" — is `LocoWheelRegister.LwrPurpose`,
   decoded by the `WheelReadingPurpose` lookup.** We already extract `LwrPurpose` as raw
   codes into Bronze, but we never extracted the lookup, so the codes were unusable.
   Adding the 13-row lookup unlocks ground-truth cut attribution for all history.
3. **Limit-crossing text on the site is exactly the approved Wrpld register**
   (`configs/limit_register_v1.json`): flange 0-3, root 0-6, tread 0-6.5 mm. The site's
   "Reason Of Turning" strings (`Root Wear limit crossed (0-6mm)`, etc.) literally encode
   the condemning values we ratified on 2026-08-19 — so this is a **cross-validation source
   for our limit register**, not just UI text.
4. **Bottleneck / limiting dimension = max utilization ratio.** For any snapshot we define
   `utilization(dim) = value(dim) / limit(dim)`; the dimension with the highest ratio is
   the bottleneck. This matches what `build_fleet_snapshot.py` (limiting_dim) and
   `models/phase5/run_turnpolicy_event_study.py` (argmax of value/limit) already do — and
   now it can be **validated against the recorded reason** instead of assumed.
5. **Data freshness:** our Bronze snapshot is stale (`LocoWheelRegister` ends 2026-08-02,
   `WheelSetMeasurements` 2026-07-24). The live DB holds the 14/08/2026 website rows (and
   beyond, to 2026-08-20). Re-extract to refresh.

---

## 1. SLAM website columns → source mapping (verified against live DB, 2026-08-20)

| # | Website column | Source table.column | Notes |
| --- | --- | --- | --- |
| 1 | S.No | row counter | presentation only |
| 2 | Loco | `LocoMaster.LomNumber` (via `LocoWheelRegister.LwrLocoId`) | physical loco number |
| 3 | HomeShed | `FunctionalLocations.FLocName/FLocCode` (`LwrFuncLocId`) | e.g. `TKDE(ELS)` = Tughlakabad; `NDLSNCR(TS)` = Secunderabad |
| 4 | Measurement DoneAt | `LwrFuncLocId` → `FunctionalLocations` | where the reading was taken (often = HomeShed) |
| 5 | Min Dia (Bogie 1) | `LwrDia1` | min diameter across bogie-1 wheelsets, stored per register row |
| 6 | Min Dia (Bogie 2) | `LwrDia2` | min diameter across bogie-2 wheelsets |
| 7 | Date | `LwrUpdatedOn` | register-row date (= measurement moment) |
| 8 | Reading Purpose | derived from `LwrTurningType` | `0` = Before Turning, `1` = After Turning, `2` = Regular CheckUp |
| 9 | Wheel Profile | `LwrWheelProfile` → `WheelProfile.WpWheelProfileName` | `1` = Thick Flange, `2` = Wear Adapted |
| 10 | Measured By | `LwrTakenBy` → `Employees.EmpFullName` | e.g. `8645` → `ANIL KUMAR MAHARIA` |
| 11 | Section | `Employees.EmpSection` → `Sections.SecCode` | e.g. `M4INSP` (SecId 28 @ TKD), `TSNDLSNCR` (SecId 3172 @ NDL) |
| 12 | **Reason Of Turning** | **`LwrPurpose` → `WheelReadingPurpose.WrpName`** | **the ground-truth cut attribution** (see §3) |
| 13 | Schedule | `LwrScheduleId` → `ScheduleTypes.SctCode/SctName` | `1`=UnSch, `5`=IA, `6`=IC, `7`=TI, `8`=IB, `10`=IOH, `12`=POH, … |
| 14 | Remarks | `LwrRemarks` | free text (e.g. `ROOT WEAR MORE JOB CARD GIVEN TO MWS.`) |

### Verified reconstruction for the website's own rows

The 20 rows pasted from the site (`39023`, `33762`, `51061`, `30397`, `41201`, `33674`,
… on 10–17/08/2026) were reproduced exactly by the query in
`sql/exploration/slam_website_view.sql`, e.g.:

| Loco | Date | ReadingPurpose | WheelProfile | MeasuredBy | ReasonOfTurning | Schedule |
| --- | --- | --- | --- | --- | --- | --- |
| 33762 | 16/08/2026 | After Turning | Wear Adapted | ANIL KUMAR MAHARIA | Root Wear limit crossed (0-6mm) | IC |
| 33762 | 15/08/2026 | Before Turning | Wear Adapted | ANIL KUMAR MAHARIA | Root Wear limit crossed (0-6mm) | IC |
| 39023 | 14/08/2026 | After Turning | Wear Adapted | ANIL KUMAR MAHARIA | Root Wear limit crossed (0-6mm) | IB |
| 51061 | 12/08/2026 | After Turning | Wear Adapted | ANIL KUMAR MAHARIA | Root Wear limit crossed (0-6mm) | IB |
| 30683 | 12/08/2026 | After Turning | Wear Adapted | ANIL KUMAR MAHARIA | Wheel Dia Matching | IC |
| 30397 | 17/08/2026 | Regular CheckUp | Wear Adapted | manoj Kumar | -- | TI |

All values match the site. **The site is a thin read-model over tables we already own.**

---

## 2. What the pipeline extracts today vs. what it is missing

### Already extracted (Bronze `loco_wheel_register.parquet`, 59,759 WAP7 rows)

`LwrId`, `LwrLocoId`, `LwrDia1`, `LwrDia2`, `LwrTurningType`, `LwrWsmSkidTurn`,
`LwrWheelProfile`, `LwrScheduleId`, `LwrStatus`, `LwrPurpose`, `LwrRemarks`,
`LwrTakenBy`, `LwrUpdatedOn`, `LwrFuncLocId`, `LwrMovId` — i.e. **every source column the
site renders.**

### NOT extracted (the decode keys — currently only 2 of these are used)

| Lookup | Rows | Why it matters | Currently used |
| --- | --- | --- | --- |
| `WheelReadingPurpose` | 13 | Decodes `LwrPurpose` → "Reason Of Turning" (the cut-attribution label) | ❌ no |
| `WheelProfile` | 2 | Decodes `LwrWheelProfile` → profile class | ❌ no (we label it `wheel_profile_2class` with raw 1/2) |
| `ScheduleTypes` | ~40 | Decodes `LwrScheduleId` → schedule code (IB/IC/IA/TI/UnSch…) | ❌ no (we keep raw `wheel_schedule_id`) |
| `Sections` | ~1,120 | Decodes section code (M4INSP etc.) | ❌ no |
| `FunctionalLocations` | ~300 | Shed / measurement-at names | ⚠️ shed via `DailyOverdueLocoCount.HomeShed` only |
| `Employees` | large | Decodes `LwrTakenBy` → measurer name | ❌ no |

### What Silver/Gold/consumers use from the register today

- `silver_gold/interval_context.py` uses only `LwrWheelProfile`, `LwrScheduleId`,
  `LwrWsmSkidTurn` (as `wheel_profile_2class`, `wheel_schedule_id`, `wheel_skid_flag`).
- `LwrPurpose` is carried raw into Bronze but **never decoded or joined** anywhere
  (candidate_source_validation.md §7.5 even flagged it "raw codes, multi-valued, needs
  mapping").
- `LwrTurningType` is deliberately excluded from turning counts (domain Q3: it is a
  post-turning reading-purpose, not a completed-event timestamp).

**Conclusion: the single most valuable field on the site — the machine-recorded reason a
loco was cut — has been sitting in our Bronze layer, unread, since the first extract.**

---

## 3. The ratio method — finding the bottleneck / limiting wear

### 3.1 Utilization ratio

For each wear dimension and the diameter, define a unitless **utilization ratio**:

| Dimension | Field | Condemning limit (Wrpld, approved 2026-08-19) | utilization |
| --- | --- | --- | --- |
| Root wear | `wsmRoot1/2` | 6.0 mm | `root / 6.0` |
| Flange wear | `wsmFlange1/2` | 3.0 mm | `flange / 3.0` |
| Tread wear | `wsmThread1/2` | 6.5 mm | `tread / 6.5` |
| Diameter | `wsmDia1/2` | 1016 mm (dead floor) | `(1096 - dia) / 80` or `(2016-dia)` style head-room |

**Bottleneck / limiting dimension = `argmax(utilization)`** — the dimension closest to (or
already beyond) its condemning value relative to its own limit. This is exactly the
normalized-margin logic already in the codebase:

- `development/dashboard/backend/build_fleet_snapshot.py:212-241` — `limiting_dim` via
  earliest within-horizon crossing, else `min(margin/limit)` per wear dim.
- `ml/models/phase5/run_turnpolicy_event_study.py:79-87` — `limiting_dim` at each turn =
  `argmax(pre_wsmFlange/3.0, pre_wsmRoot/6.0, pre_wsmThread/6.5)`.

### 3.2 Why all three wears drop at a cut — and what actually caused it

At a turning (reprofit), the lathe removes material across the whole profile, so **flange,
root, tread AND diameter all move at once**. You cannot infer the cause from the post-cut
row. You can only attribute the cause from the **pre-cut state**:

1. Take the measurement immediately **before** the turning (the `Before Turning` row via
   `LwrTurningType=0`, or the last pre-turn `WheelSetMeasurements` row before the
   `wsmturning=1` event).
2. Compute `utilization` for flange/root/tread on that pre-turn state.
3. The dimension with `utilization ≥ 1` (limit crossed) — or the one closest to 1 — is the
   **bottleneck / limiting wear** that drove the cut.

**Ground-truth validation (new):** the site's **Reason Of Turning** (`LwrPurpose` →
`WheelReadingPurpose`) records the shed's own judgement per register row. Mapping:

| Code | Website text | Meaning |
| --- | --- | --- |
| 1 | Bogie Balancing | wheel-balance action |
| 2 | Bogie Changing | |
| 3 | Flange Wear limit crossed (0-3mm) | flange = 3.0 condemning (Wrpld) |
| 4 | Normal Wear | routine; no limit crossed |
| 5 | FW/RW | flange + root wear |
| 6 | Pitting Marks | surface defect |
| 7 | Root Wear limit crossed (0-6mm) | **root = 6.0 condemning (Wrpld)** |
| 8 | Tread Wear limit crossed (0-6.5mm) | **tread = 6.5 condemning (Wrpld)** |
| 9 | Wheel Dia Matching | diameter mismatch across wheelsets (not a wear crossing) |
| 10 | Wheel Skidding | skid flat |
| 11 | Others | |
| 12 | Scratching Marks | |
| 13 | Metal Chip Out | |

So for every historical cut we can answer: **"was it cut because root reached its limit, or
flange, or tread, or diameter-matching?"** — from a field we already extract — and then
**check whether the ratio `argmax` we compute agrees with the recorded reason.** This turns
our current assumed bottleneck into an evidence-backed one.

### 3.3 Example from the verified rows

- `33762` 15/08 pre-turn, reason = "Root Wear limit crossed (0-6mm)", schedule IC →
  root is the driver. Ratio check on the pre-turn `WheelSetMeasurements` row for that
  wheelset should show `root/6.0` highest (or ≥1).
- `30683` 12/08 reason = "Wheel Dia Matching" → not a wear crossing; the driver is
  diameter spread across the 12 wheels, i.e. our `limiting_dim` should label it `wsmDia`
  (or a wheel-set-diameter-mismatch flag), which the current snapshot logic already
  special-cases via `days_to_condemning_dia`.
- `41201` 13/08 reason = "Normal Wear", UnSch → no limit crossed; our P(turn) model and
  utilization ratios should reflect low urgency.

---

## 4. Value assessment

| Field | Value | Priority |
| --- | --- | --- |
| **Reason Of Turning (`LwrPurpose` + `WheelReadingPurpose`)** | **Highest** — ground-truth label for "why a loco was cut"; enables (a) supervised attribution, (b) validation of our limiting-dim logic, (c) cross-validation of the Wrpld limit register, (d) a check on the flag-based turning events | **Add now** |
| Reading Purpose (`LwrTurningType`) | High — cleanly splits before/after/regular, sharpens interval semantics and event detection | Already extracted raw; just encode |
| Wheel Profile (`WheelProfile`) | Low-Moderate — 2 classes only; already carried as 2class | decode it |
| Schedule (`ScheduleTypes`) | Moderate — maintenance context for "was the cut at an A/B/C/TI schedule or unscheduled" | decode it |
| Measured By / Section / HomeShed | Low for modelling, high for governance/audit & shed-policy studies | decode if cheap |
| Min Dia Bogie1/2 (`LwrDia1/2`) | High — already the basis of `LwrDia`; matches our wheelset-dia logic | already extracted |

**What it unblocks (previously blocked/assumed):**

- `limiting_dimension` becomes a **validated** output, not a heuristic (compare computed
  argmax vs recorded reason per cut).
- Turning-event recovery improves: a `Before Turning` register row with reason code
  ≠ "Normal Wear" is corroborating evidence even when `wsmturning` flag is absent.
- Limit register (`configs/limit_register_v1.json`) gains an independent, operationally
  observed confirmation of 3.0 / 6.0 / 6.5 mm.

---

## 5. Data freshness / database landscape

- The **only accessible SLAM DB** with these tables is `SLAM_PROD_DB_10.05.2022`
  (server `10.30.4.18`). Other databases exist on the server (`JC_MEASUREMENTS`,
  `ELS_STAGING_DB_TEMP`, `TSTLC_STAGING_DB_TEMP`, `distribution`, `model`, `msdb`,
  `tempdb`) but the current credentials cannot access them (permission denied 916) and none
  contain the wheel register.
- **Live DB is current:** `LocoWheelRegister` max `LwrUpdatedOn = 2026-08-20`;
  `WheelSetMeasurements` max `wsmUpdatedOn = 2026-08-20`. The website's 14/08/2026 rows for
  `39023`/`33762`/`51061` are present in the live DB.
- **Our Bronze extract is stale:** `LocoWheelRegister` ends 2026-08-02
  (extracted 2026-08-03), `WheelSetMeasurements` ends 2026-07-24. **Re-extraction is
  required to see the 14/08/2026+ data in the pipeline.**
- Partitions: rows with `LwrId ≥ 238014` / `wsmWRId ≥ 238014` (Jul 2026 onward) live only in
  `LocoWheelRegister_LwrId_238014_238028` / `WheelSetMeasurements_wsmWRId_238014_238028` —
  extraction queries must include these companion tables or the fresh rows will be missed.

---

## 6. Recommended actions and status

1. ✅ **Add four-to-six lookup extracts** (done 2026-08-20, see `sql/extraction/`):
   `wheel_reading_purpose.sql`, `wheel_profile.sql`, `schedule_types.sql`,
   `sections.sql`, `functional_locations.sql`, `employees.sql`.
2. ✅ **Encode `LwrPurpose` / `LwrTurningType`** into `reason_of_turning`,
   `reason_of_turning_raw_codes`, `reading_purpose` decodes in
   `silver_gold/interval_context.py` (uses `configs/wheel_reference_decode_v1.json`).
   Unknown codes are conserved verbatim so nothing is silently dropped.
3. ⏳ **Refresh Bronze** for `loco_wheel_register`, `wheel_measurements`, and the Jul-2026
   partition tables (`LocoWheelRegister_LwrId_238014_238028` /
   `WheelSetMeasurements_wsmWRId_238014_238028`) so the 14-20/08/2026 data enters the
   lake. **Still outstanding** — bronze ends 2026-08-02 register / 2026-07-24 measurements.
4. ✅ **Validation study** (done 2026-08-20, `models/phase5/run_reason_of_turning_validation.py`
   → `report/reason_of_turning_validation.json`). For each turning event with a pre-turn
   state it compares ratio-argmax (`argmax(value/limit)`) against the recorded reason.
5. ✅ **`limiting_dim` + `limiting_dim_source` contract** (done 2026-08-20): `silver_gold/interval_context.py` now emits `limiting_dim` ({flange, root, tread, dia, other}), `limiting_dim_source` ({recorded_reason, ratio_calibrated, predicted}), `utilization_{flange,root,tread}` and `limiting_dim_prior`. Fleet priors are applied only when `recorded_reason` is absent; recorded-reason provenance is never overwritten. Verified on fresh Bronze: 225,262 intervals; recorded_reason 119,142 / ratio_calibrated 106,120; priors 0.63/0.53/0.81 applied on ratio rows only.

### Validation study headline results (2026-08-20, bronze snapshot)

| Metric | Value |
| --- | --- |
| Turns with usable pre-turn state | 40,044 |
| Ratio `limiting_dim` (argmax value/limit) | root 20,545 (51%), flange 16,453 (41%), tread 3,046 (8%) |
| Recorded reason coverage | sparse — only ~1,428 turns carry a real purpose code (sentinel `0`/"No Reason Recorded" on the rest, consistent with `LwrStatus=0` rows) |
| Recorded class among covered turns | wear 797, dia 469, other 162 |
| Of the 797 wear-recorded turns, ratio-argmax says | flange 521 (65%), root 166, tread 110 |

Readings:

- **Root dominates as the ratio bottleneck** (51% vs ~3-8% recorded "Root Wear limit
  crossed"). The two disagree at scale: sheds cut mostly citing **flange / FW-RW**
  while the ratio method labels root first. This is the key caveat from §3.3 — the
  operator records the *justification*, not necessarily the mechanically-nearest-limit
  dimension, and root sits closest to its (6.0 mm) limit even at low absolute wear.
- Because recorded coverage is low (~3.6% of turns), **agreement overall is 2.4%**; the
  comparison is only meaningful on the coverage subset and per shed.
- **Conclusion:** the ratio method is a *necessary* engineering prior but is not yet
  *sufficient* as a bottleneck label — it needs the recorded reason (when present) plus a
  shed-level calibration. Do NOT consume `reason_of_turning` as a verified label alone.
- Notably, when sheds *do* record a wear reason it is flange/FW-RW heavy (797 wear rows:
  flange-class 271 + FW/RW 520), which matches the ratio method's *second* candidate.
  So the practical recommendation is: bottleneck = `recorded_reason` when present,
  else ratio-argmax calibrated per shed — never ratio alone.

---

## 7. References

- `configs/limit_register_v1.json` — approved Wrpld limits (flange 3.0 / root 6.0 / tread 6.5 mm).
- `validation/candidate_source_validation.md` — §7.5/7.5a/7.7 register semantics.
- `docs/domain_owner_questions.md` — Q3 (`LwrTurningType` is reading-purpose, not event).
- `sql/exploration/slam_website_view.sql` — the verified reconstruction query.
- `development/dashboard/backend/build_fleet_snapshot.py` — current limiting-dim logic.
- `ml/models/phase5/run_turnpolicy_event_study.py` — current argmax(value/limit) per turn.

## 8. Change log

| Date | Change |
| --- | --- |
| 2026-08-20 | Initial mapping verified against live `SLAM_PROD_DB_10.05.2022`; SLAM website columns fully decoded; `LwrPurpose` identified as the ground-truth Reason-Of-Turning label; ratio (utilization) method documented as the bottleneck-attribution rule; Bronze freshness gap and partition tables documented. |
| 2026-08-20 | Added six lookup extraction SQLs, a reconstruction view (`sql/exploration/slam_website_view.sql`), a verified decode config (`configs/wheel_reference_decode_v1.json`), wired `reason_of_turning`/`reading_purpose` decodes into `silver_gold/interval_context.py`, and ran the first validation study comparing ratio-argmax vs recorded reason (`models/phase5/run_reason_of_turning_validation.py`). |
| 2026-08-20 | **Live Bronze refreshed** via `scripts/refresh_bronze.py`: register 60,587 rows (max 2026-08-20 06:48), measurements 1,192,945 rows (max 2026-08-20 12:31), plus 6 lookups (WheelReadingPurpose 13, WheelProfile 2, ScheduleTypes 77, Sections 2,534, FunctionalLocations 389, Employees 57,416) and 2 partition-probe tables. Website 14-20 Aug rows present (219 register rows ≥ 2026-08-14). No duplicate keys. | 
| 2026-08-20 | **Partition tables re-classified:** `LocoWheelRegister_LwrId_238014_238028` (15 rows) and `WheelSetMeasurements_wsmWRId_238014_238028` (90 rows) are a **WAG9HC staging copy, NOT WAP7 partitions** — 0/15 and 0/90 IDs exist in the main tables and all 15 register rows are WAG9HC. They are irrelevant to the WAP7 cohort and are **not** the source of missing August rows. Main tables are the authoritative superset. |
| 2026-08-20 | **Validation rerun on fresh Bronze:** 41,276 turns with pre-state (+1,232 vs baseline). Ratio `limiting_dim`: root 50.9% (baseline 51%), flange 41.4% (41%), tread 7.7% (8%). Recorded reasons remain flange/FW-RW heavy (wear-class 822 rows: ratio says flange 538/822). Agreement 2.42%. **Conclusion unchanged** — the pattern survives August data; keep recorded-reason-when-present, ratio-per-shed otherwise, never ratio alone. |
| 2026-08-20 | **Attribution calibration (fresh):** `models/phase5/run_attribution_calibration.py` → `report/attribution_calibration.json`. Fleet-level prior P(recorded wear | ratio=dim): flange **0.63**, root **0.53**, tread **0.81** (only among turns that recorded a wear reason). Coverage limitation: only 29.6% of turn-event register refs are in the WAP7 register (wheelsets migrate between locos), so shed-level attribution is meaningful only for ~12k/41k turns; 14 sheds have ≥20 turns. Reuses the shared turn-event reconstruction (`_turn_event_lib.py`) so it is identical to the validation study. |
| 2026-08-20 | **Gold contract emitted:** `interval_context` now emits `limiting_dim`, `limiting_dim_source`, `utilization_{flange,root,tread}`, `limiting_dim_prior` using the calibrated fleet priors (recorded_reason when present, ratio_calibrated otherwise). Pure data-layer change; no model re-training. Downstream consumers (fleet snapshot, event study, dashboard) can now separate verified from inferred attribution. |

## 9. Checkpoint — Engineering Truth layer

> **SLAM Reason-of-Turning provenance: DONE** (field provenance + decode + validation study + live lookup extraction)
> **Fresh August Bronze: DONE** (register & measurements to 2026-08-20; Gold interval-context rebuilt)
> **Attribution calibration: DONE (fresh-data)** — fleet priors estimated (flange 0.63 / root 0.53 / tread 0.81); shed-level calibration limited to ~30% of turns by wheelset-migration coverage
> **Gold contract (`limiting_dim` + `limiting_dim_source`): DONE** — emitted into `interval_context`, calibrated priors applied only where recorded reason is absent
>
> **Architecture unchanged.** This fills a previously missing semantic key (`reason_of_turning`); it does not warrant a rewrite. Attribution is provenance-tagged (`recorded_reason | ratio_calibrated | predicted`); no model trains on `reason_of_turning` as a label yet.

## 10. Measurement scope gate — trip-shed exclusion

Trip-shed and other designated non-home / non-inspection measurements must not
enter lifecycle series, lifecycle turns, or any feature substrate feeding a
forecast. The shared policy is implemented in
`models/phase5/measurement_scope.py` and registered in
`configs/measurement_scope_v1.json`; it is applied before lifecycle boundary
construction and serving feature extraction. The dashboard chart must therefore
not solve this as a display-only filter.

**Domain-owner confirmation required before release:** provide the exact
`FunctionalLocations.FLocCode/FLocName` values and `Sections.SecCode` values for
trip-shed and any other non-inspection locations. Add those values to the scope
register, refresh lifecycle artifacts, rebuild forecast substrates/snapshots,
and report excluded-row counts. Until then, the policy only covers the
explicitly configured trip-shed labels and environment override
`WHEEL_EXCLUDED_LOCATION_CODES`.

**Database audit completed 2026-08-21:** live `SLAM_PROD_DB_10.05.2022` returned
FunctionalLocations `CHZ` (Trip Shed Charlapalli) and `DBRG` (Trip Shed DBRG),
plus Sections `T/SHED`, `VMET`, `TS`, `SVDKAdmin`, `Trip shed BCT`, `KSJ`,
`TSJBP` and the linked `CHZStore`, `CHZAdmin`, `DBRGStore`, `DBRGAdmin` rows.
The current live WAP7 register has zero rows at those trip-shed functional
locations and zero rows through those trip-shed sections. These are now
registered as DB-verified exclusions; domain sign-off is still required before
calling the scope contract final.
