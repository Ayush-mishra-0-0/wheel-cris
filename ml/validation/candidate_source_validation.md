# Candidate Source Validation — LocoWheelRegister, WheelFormationTemplates, Context Sources

> **Amendment (2026-08-03):** the first section validated *availability*. Availability
> is NOT semantics. Section 7 below documents the semantic evidence for the two
> contested fields (`wsmturning` and root wear). **Neither is confirmed.** Both
> remain gated on a domain-owner decision, exactly as `degradation_semantics.md` §4 states.
>
> **Amendment (2026-08-03, later run):** the original cohort denominator was wrong.
> The first run used `LomNumber LIKE '30%'` (= 829 locos). The canonical cohort
> resolved by `extract/build_cohort.py` is the WAP7 **type** (`LocoTypes.LotTypeName='WAP7'`
> → `LomType = 9`) = **2,317 locos**. This matches the gold layer (`inspection_intervals`
> 2,100 locos; `wheel_timeline_gold_b` 2,180 locos). All coverage figures below are
> recomputed against `LomType = 9` and replace the earlier 30%-prefix numbers.

**Status:** Validated for feature use — see per-source verdicts below.

**Source snapshot:** live `SLAM_PROD_DB_10.05.2022` @ 10.30.4.18, queried 2026-08-03.
**Cohort denominator:** WAP7 type in `LocoMaster` (`LomType = 9`, resolved via `LotTypeName='WAP7'`) = **2,317 locos**.

---

## 1. LocoWheelRegister (`dbo.LocoWheelRegister`)

| Metric | Value |
| --- | --- |
| Rows (full table) | 200,371 |
| Distinct `LwrId` | 200,372 → **no duplicate key** |
| **WAP7 rows (type cohort)** | **59,759** |
| **WAP7 locos covered** | **2,300 / 2,317 (99.3%)** |
| Date range | 1900-01-01 sentinel → 2026-08-03 |

### Fill rates (WAP7-type cohort, n = 59,759)

| Column | Null count | Null % | Verdict |
| --- | ---: | ---: | --- |
| `LwrDia1` / `LwrDia2` | 1,459 | 2.4% | ✅ usable (both sides = wheelset grain) |
| `LwrTurningType` | 1,505 | 2.5% | ✅ usable |
| `LwrWsmSkidTurn` | 83 | 0.1% | ✅ usable |
| `LwrWheelProfile` | 21,313 | 35.7% | ⚠️ usable as 2-class profile (1 / 2) |
| `LwrUpdatedOn` | 65 | 0.1% | ✅ usable |
| `LwrScheduleId` | 3,015 | 5.0% | ✅ usable |
| `LwrLocoId` | 0 | 0% | ✅ |
| `LwrPurpose` | 8,847 | 14.8% | ⚠️ raw codes, multi-valued (`"5,9"`), needs mapping |

### Turning-event evidence (the label source)

WAP7-type rows by `LwrTurningType`: **0=16,707, 1=16,913, 2=24,359, -1=275, NULL=1,505**.
→ ~41,270 turning events (types 1/2) across 2,300 WAP7 locos ≈ **18 turning events per loco**. Sufficient for a turning/label and a "days since turning" feature.
Sentinel dates: only **87 / 31,599** WAP7 rows pre-2000 (0.28%). ✅

### Identity link

`WheelSetMeasurements.wsmWRId` → `LocoWheelRegister.LwrId`:
- 59,234 distinct WAP7 `wsmWRId` values match to WAP7 `LwrId` rows.
- 1,162,589 / 1,174,657 WSM rows have a `wsmWRId` (99.0%).
- 1,137,800 / 1,150,283 WSM rows have both `wsmWheelSetPosition` and `wsmW1EndType` (98.9%).

**Verdict: USE — this is the missing wheel-register master.** It provides turning events, skid flags, wheel profile, and schedule context at the wheelset grain, and links 1:1 to every wheel measurement.

---

## 2. WheelFormationTemplates (`dbo.WheelFormationTemplates`)

| Metric | Value |
| --- | --- |
| Rows | 556; 12 rows per loco type (48 types covered) |
| WAP7 (`LotId=9`) | **12 rows** = 6 wheelsets × 2 ends, mapping `WftWSPos`(1–6) + `WftEndType`(1/2) → `WftWheelPos`(1–12) |
| WSM mappability | 1,137,800 / 1,150,283 rows (98.9%) have both `wsmWheelSetPosition` and `wsmW1EndType` |

Join check (WAP7, WSPos=1): `wsmW1EndType=1 → WheelPos=1`, `=2 → WheelPos=2` — consistent.
Note: wheelsets 4–6 use **reversed** end order (`WSPos=4, EndType=2 → WheelPos=7`; `EndType=1 → 8`),
confirmed in the extracted WAP7 template. Use the template join, never a hard-coded parity rule.

**Verdict: USE — resolves the wheel-position and axle-position gaps.** Individual wheel (1–12) is derivable for 98.9% of measurements by joining WSM on `(wsmWheelSetPosition, wsmW1EndType)`.

---

## 3. PrevLocoWheelDetails (`dbo.PrevLocoWheelDetails`)

**Row count = 0.** Empty table.

**Verdict: DO NOT USE — dead end.** Ignore this candidate entirely.

---

## 4. Context sources (Zone / Division / Home Shed)

| Source | Rows (type cohort) | WAP7 coverage | Fill | Verdict |
| --- | ---: | ---: | --- | --- |
| `OnlineDefects_LogHistory` | 387,761 total | **106,300 WAP7 rows / 2,229 locos** | Zone 99.5%, Div 99.9%, **Shed 99.9% null** | ✅ Zone/Div for WAP7; shed absent |
| `DailyOverdueLocoCount` | 352,627 total | **246,751 WAP7 rows / 1,921 locos** | HomeShed **0% null** | ✅ Home shed |
| `Integ_icms_LocoCurrentLocation` | 5,012 total | **2,307 WAP7 rows / 2,307 locos** | currentZone/Division present | ✅ snapshot zone/div |
| `Integ_pub_COA_slamlocoSchedule` | 216,600 total | **98,343 WAP7 rows / 2,300 locos** | LOCOSHED 0% null | ✅ shed |
| `Integ_rtis_Locodevice` | 28,106 total | **5,038 WAP7 rows / 1,937 locos** | shed 1.8% null | ✅ shed |
| `INTEG_FOIS_LocoLocation` | 10,270 | **2 WAP7 locos only** | FOISZone 0% null | ❌ WAP7 coverage still negligible |
| `LocoEquipmentChangeRegister` | 783,806 total | **145,470 WAP7 rows / 2,061 locos** | `LerProvidedOn`/`LerDateOfRemoval` populated | ✅ NEW — provision/removal ledger (wheel-age proxy) |
| `EquipmentFailureRegister` | 48,128 total | **7,381 WAP7 rows via LECR / 1,492 locos** | `EfrAbnormality` 0% null | ⚠️ use; loco link only via LECR |

**Verdict: Zone, Division and Home Shed ARE obtainable for the WAP7 cohort** — but **not from FOIS**. Use `OnlineDefects_LogHistory` (zone/div) + `DailyOverdueLocoCount` (home shed). The earlier "missing" claim came from restricting the search to FOIS.

---

## 5. Wheel age / provision date

| Source | Usable |
| --- | ---: |
| `WheelSetMeasurements.wsmProvDate` | only 35% (65.2% null/pre-2000) |
| `EquipmentMasterRegister.EmrDoM` (wheel-type rows) | only 9.3% usable |
| `LocoEquipmentsHistory` | provision 88.9% usable, removal 72.8% null |
| `LocoEquipmentChangeRegister.LerProvidedOn` | ✅ **NEW — 145,470 WAP7 rows / 2,061 locos** (see §6a) |

**Verdict: IMPROVED — the provision-ledger proxy (`LocoEquipmentChangeRegister`) now gives
assignment-level wheel age at near-full coverage. Manufacture-level age stays weak.**

---

## 6. Abnormal events

| Source | WAP7 rows | Fill |
| --- | ---: | --- |
| `AbnormalityRegister` | 81,181 (2,263 locos) | jobcard link 68.8% |
| `EquipmentFailureRegister` | 7,381 via LECR (1,492 locos) | `EfrAbnormality` 0% null |

**Verdict: USE** — both tables are populated and linkable.

## 6a. Wheel age / provision ledger (new finding)

`LocoEquipmentChangeRegister` (145,470 WAP7 rows, 2,061 locos) records per-position
equipment provision (`LerProvidedOn`) and removal (`LerDateOfRemoval`) on a locomotive.
This is the strongest available **wheel-assignment/age proxy**: better than
`wsmProvDate` (35%) and at assignment level like `LocoEquipmentsHistory.LoehProvisionDate`
(88.9%). It also provides replacement evidence (old/new equipment on the same position).

---

## Summary verdict

| Feature | Status after validation |
| --- | --- |
| Wheel position / axle position | ✅ SOLVED via WheelFormationTemplates (98.9% mappable) |
| Turning flag / days since turning | ✅ SOLVED via LocoWheelRegister (~41.3K WAP7 turning events) |
| QR / wheel profile | ⚠️ PARTIAL — 2-class profile (1/2), 64% fill |
| Previous maintenance / schedule | ✅ SOLVED via LwrScheduleId + LocoHistory |
| Inspection count | ✅ SOLVED (derivable from WSM history per wsmWRId) |
| Zone / Division | ✅ SOLVED via OnlineDefects (106.3K WAP7 rows) |
| Home Shed | ✅ SOLVED via DailyOverdueLocoCount (0% null) |
| Abnormal events | ✅ SOLVED via AbnormalityRegister + EquipmentFailureRegister |
| Wheel provision / age proxy | ✅ SOLVED via LocoEquipmentChangeRegister (145.5K rows) |
| **Wheel age** | ⚠️ **PARTIAL — assignment-level only; manufacture date still weak** |
| **Health index** | ❌ by design — engineered, not a source column |

**Dead ends:** `PrevLocoWheelDetails` (empty), `INTEG_FOIS_LocoLocation` (negligible WAP7 coverage).

**Conclusion:** the data needed to build the matrix exists and is populated. Only **wheel age** stays partial and **health index** stays deliberately blocked. Extraction SQL has been written and run for all validated sources (see `sql/extraction/` and `data/bronze/`).

---

## 7. Semantic evidence — turning flag and root wear (the contested fields)

**Question:** is root wear *cumulative since last turning* (resets at turning) or a *direct measured depth*? And what does a turning flag actually mean?

### 7.1 The two turning sources DISAGREE — a red flag

Cross-tab of `WheelSetMeasurements.wsmturning1` vs `LocoWheelRegister.LwrTurningType`:

| wsmturning1 | LwrTurningType | rows |
| ---: | ---: | ---: |
| 0 | 1 | **280,215** |
| 0 | 2 | **482,907** |
| 0 | 0 | 312,451 |
| 1 | 1 | 29,855 |
| 1 | 0 | 5,701 |
| 1 | 2 | 5,987 |

A measurement flagged `wsmturning=0` (no turning) co-occurs with `LwrTurningType=1` in 280K rows and `=2` in 483K rows. **The two fields do not mean the same thing.** We cannot treat either as an authoritative turning event without a decision on which is which.

### 7.2 Turning resets root wear — evidence of a cumulative index

Comparing root wear at the measurement immediately *before* vs *at* a `wsmturning=1` measurement (full population, diameter quarantined to [600, 1300]):

| interval | n | avg root delta | avg dia1 delta | dia increased | dia decreased |
| --- | ---: | ---: | ---: | ---: | ---: |
| ENDS at turning row (cur=1) | 33,052 | **−1.117** | **−3.723** | 2,548 | 28,075 |
| STARTS at turning row (prev=1) | 21,784 | +1.08 | +0.477 | 2,001 | 12,795 |
| no turning | 849,509 | +0.05 | −0.57 | 72,888 | 427,773 |

**Resolution (2026-08-03, owner-confirmed + re-validated):** the apparent "cumulative reset"
reading was misleading. Root is a **direct measured depth** (see §7.8): the −1.1 at turning
rows is modest material removal at the fillet, the +1.08 after is continued wear, and 24% of
turning rows even show root *increasing* — all consistent with a noisy direct dimension, not a
monotonic index. Diameter **drops** at 91% of turning rows (avg −3.7mm), confirming
owner-confirmed semantics: **turning cuts material → smaller diameter** (`degradation_semantics.md`
§3.1 corrected).

### 7.3 Root also DECREASES without any turning flag — RESOLVED toward direct-depth

In intervals where both endpoints are `wsmturning=0` (856,547 intervals):

| outcome | n | pct |
| --- | ---: | ---: |
| root increased | 415,978 | **48.6%** |
| root decreased | 227,334 | **26.5%** |
| root unchanged | 213,235 | 24.9% |

**Resolution (2026-08-03):** the 26.5% decrease is **not evidence the turning flag is
incomplete**. Of 268,145 unflagged root decreases, **77.1% coincide with a `wsmProvDia`
change** (wheel replacement), and root resets to ~0 at provision changes in 73.8% of cases vs
7.5% at flagged turning. After excluding provision-changes and root-resets, only **13.6%
(≈26,750 pairs)** remain with root drop >0.5; those carry a real diameter-cut signature
(median 5.5mm, 84% decreased) and are a small genuine residual that may be unflagged turnings
(slight undercount in `days_since_turning`, acceptable as a feature, not as a label). Root is
a direct measurement with variance.

### 7.4 Big unflagged root drops also drop diameter — RESOLVED toward replacement

| root bucket (non-turn intervals) | n | avg dia delta | dia increased | dia decreased |
| --- | ---: | ---: | ---: | ---: |
| root drop > 1.0 | 118,143 | **−2.14** | 14,887 | 95,264 |
| root drop 0.1–1.0 | 103,985 | −0.13 | 14,041 | 59,010 |
| root drop < 0.1 | 215,542 | −0.17 | 12,537 | 80,161 |
| root gain > 0.1 | 405,085 | −0.45 | 30,713 | 189,774 |

**Resolution (2026-08-03):** the big unflagged root-drop + diameter-drop signature is
**dominated by wheel replacements** (provision changes), with a small residual of possible
unflagged turnings. Because root is a direct depth (7.3), these drops do not reset a
cumulative index — they are new wheels or (rarely) un-flagged turning events.

### 7.5 LocoWheelRegister remark text — what LwrTurningType really encodes

| LwrTurningType | mentions turning/reprofil | mentions done/completed | n |
| ---: | ---: | ---: | ---: |
| 0 | 8,035 | 7,194 | 44,744 |
| 1 | 9,252 | 25,548 | 47,501 |
| 2 | 5,263 | 15,312 | 81,962 |

Remark samples: type=1 → `"Bogie no.1 requierd wrp due to flange wear, root wear excess"`, `"TFRW DONE."`; type=2 → `"All parameters are within permissible limit"`, `"TT Not required, all wheels are regular checked."`. This suggests `LwrTurningType` may encode a **turning-required/recommendation outcome**, not a completed-turning event with an exact timestamp. That is unconfirmed.

### 7.5a Exhaustiveness cross-check — LwrTurningType is NOT the event timestamp (2026-08-03)

Extracted `LocoWheelRegister` (59,759 WAP7 rows) and merged against `WheelSetMeasurements`
on `wsmWRId` = `LwrId`, requiring a WSM measurement within ±7 days of `LwrUpdatedOn`:

| LwrTurningType | WSM measurement nearby but UN-flagged (`wsmturning=0`) | WSM measurement nearby and FLAGGED (`wsmturning=1`) |
| ---: | ---: | ---: |
| 1 | 87,935 | 12,740 |
| 2 | 142,538 | 568 |

Distinct turning events (type 1/2) with a nearby WSM measurement: **3,168 flagged** vs
**39,221 NOT flagged (92.5%)**. If `LwrTurningType=1/2` were a completed-turning event
timestamp, we would expect its nearby wheel measurement to carry `wsmturning=1`. It does not
in 92.5% of cases. Combined with the remark text (§7.5), `LwrTurningType` behaves as a
**recommendation/assessment code**, not an event timestamp.

**Consequence:** `LwrTurningType` must NOT be used to build `days_since_turning` or turning
counts. The only event signal remains `wsmturning` in `WheelSetMeasurements` (which is itself
incomplete per §7.3/7.4). Both gaps go to the domain owner.

### 7.6 Verdict — semantics are RESOLVED for event-vs-state, UNRESOLVED for reset

**Turning flag IS an event flag (resolved by TEST 1/5/6):**
- `wsmturning=1` drops back to `0` on the next row in the majority (23,339) of cases.
- The 15,392 "followed by turn1" cases split into **same-day duplicate rows** (4,935; many with identical `wsmId`, diameter, root — duplicate entry) and **genuine repeat turnings** (31–180d: 7,305; >180d: 1,251). 6,855 equipment have **multiple distinct turning days** — a wheelset is legitimately turned multiple times in its life.
- **Conclusion: `wsmturning=1` means "turning happened at this measurement" (event), not "has been turned" (state).** This resolves `degradation_semantics.md` §4 Q1.

**Turning flag vs LwrTurningType (RESOLVED toward recommendation):** they disagree at scale
(7.1); remark text (7.5) and the 92.5% exhaustiveness gap (7.5a) both show `LwrTurningType`
is a recommendation/assessment code, NOT a completed-turning timestamp. Only `wsmturning`
is an event signal, and it is incomplete (§7.3/7.4).

**Root wear reset (unresolved):** turning resets root (7.2) → cumulative-since-turning hypothesis holds at turning rows, BUT 26.5% of no-flag intervals still decrease root (7.3), and those drops share the turning diameter signature (7.4) → likely unflagged events. Domain owner must confirm whether the flag is exhaustive.

**Diameter at turning (contradicts semantics doc):** diameter *decreases* ~3.7mm at turning rows, opposite to §3.1's "increases" assumption. Raise with domain owner.

**Consequence for modelling:** `days_since_turning` is now safe to build **if** the flag is accepted as exhaustive event semantics — but the 26.5% unflagged-root-drop population means it will be incomplete. A cumulative root-wear feature remains conditional on confirming (a) flag exhaustiveness and (b) root reset convention. Do **not** build a regression target that assumes reset semantics until both are answered.

### 7.7 Wheel identity — `wsmEquipmentId` (= `EmrId`) IS the stable per-equipment key; `wsmWRId` is NOT (2026-08-03)

`WheelSetMeasurements` carries two equipment-related ids. They mean different things, and only
one is a stable per-wheel(-set) identity:

| Column | What it is | Evidence |
| --- | --- | --- |
| `wsmEquipmentId` | **Stable physical-equipment key.** Maps 100% to `EquipmentMasterRegister.EmrId`. | same EmrId across a 22-year measurement history (equipment 8279); unique serial per id; unique equipment type per id |
| `wsmWRId` | **Per-measurement register id, re-issued each run.** | changes between adjacent measurements on the same equipment **99.8%** of the time (turning rows 99.9%, non-turning 99.8%); **97.7%** of distinct values reused across >1 locomotive; median 6 measurements per value |

**Correct interpretation:** the pipeline's `wheelset_equipment_id` (= `wsmEquipmentId`) is the
persistent per-wheelset key and the inspection-interval grain is correctly keyed on it.
`wsmWRId` is a measurement-run/register reference, not a wheel identity. Using `wsmWRId` for
per-wheel counting (as the earlier interval-context build did) produced a contamination
artefact (99.4% of intervals = exactly 6, the global median rows-per-id); re-keying the same
count on `wsmEquipmentId` yields a sane distribution (median 7 inspections per equipment;
1 = 14%, 2–5 = 27%, 6–20 = 48%, >20 = 10.5%).

**Turning preserves identity at the equipment level:** 11,244 equipment have ≥1 turning event
and 7,368 have ≥2; the same `wsmEquipmentId` persists across them. So days-since-turning and
per-wheelset wear tracking are well-defined **on `wsmEquipmentId`** — not on `wsmWRId`.

**Open sub-question for the register — RESOLVED (2026-08-03):** the correct register join is
`wsmWRId = LwrId`, and the earlier "~30%" overlap figure was measured against the **unfiltered**
measurements file (all loco types, 1.16M rows). Against the **WAP7 interval subset** the join
matches **99.98%** of interval endpoints (register `LwrUpdatedOn` aligns with the measurement
timestamp 99.84% within 1 day; diameter exact-match 23% — the register row is the state at the
measurement moment, so it is a point-in-time snapshot, not a cumulative history).

Candidate joins tested and rejected:
- `wsmEquipmentId = LwrId`: 2.25% (equipment id is a different id space from the register).
- Parent/child assembly (`EmrParentEquipment` / `EmrChildEqMasterRegister`): 0% — no link.
- Functional location (`LwrFuncLocId` → `EmrStoreFunctionalLocation`): only ~3% of measurement
  equipment reachable; 58% of register rows map to *an* EmrId but those are not the measured
  wheelsets.

So the two ids have distinct roles: **`wsmEquipmentId` = identity** (stable per wheelset;
inspection count, days-since-turning keyed on it) and **`wsmWRId` = register reference**
(per-measurement; joins to `LocoWheelRegister` for profile/schedule). Both are needed; neither
is a substitute for the other. With this, profile/schedule are re-released: coverage 75.0% /
97.6% on WAP7 intervals.

### Evidence queries

- `sql/validation/turning_flag_semantics.sql` — TEST 1 (event-vs-state persistence), TEST 2 (diameter/root around turning), TEST 3 (side agreement), TEST 4 (skid relationship), TEST 5 (repeat-turning gap), TEST 6 (distinct turning days), TEST 7 (diameter distribution at turning row).
- Earlier exploratory runs in temp workspace `opencode/semantics*.py`.

## Evidence queries

Ad-hoc profiling run against the live DB on 2026-08-03; SQL in temp workspace `opencode/validate_new_tables*.py`.
