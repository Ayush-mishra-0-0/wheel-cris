# Candidate Source Validation — LocoWheelRegister, WheelFormationTemplates, Context Sources

> **Amendment (2026-08-03):** the first section validated *availability*. Availability
> is NOT semantics. Section 7 below documents the semantic evidence for the two
> contested fields (`wsmturning` and root wear). **Neither is confirmed.** Both
> remain gated on a domain-owner decision, exactly as `degradation_semantics.md` §4 states.

**Status:** Validated for feature use — see per-source verdicts below.

**Source snapshot:** live `SLAM_PROD_DB_10.05.2022` @ 10.30.4.18, queried 2026-08-03.
**Cohort denominator:** WAP7 locos in `LocoMaster` with `LomNumber LIKE '30%'` = **829 locos**.

---

## 1. LocoWheelRegister (`dbo.LocoWheelRegister`)

| Metric | Value |
| --- | --- |
| Rows | 200,371 |
| Distinct `LwrId` | 200,372 → **no duplicate key** |
| Distinct locos | 14,224 |
| WAP7 locos covered | **828 / 829 (99.9%)** |
| Date range | 1900-01-01 sentinel → 2026-08-03 |

### Fill rates (WAP7-relevant columns)

| Column | Null % | Verdict |
| --- | ---: | --- |
| `LwrDia1` / `LwrDia2` | 2.2% | ✅ usable (both sides = wheelset grain) |
| `LwrTurningType` | 2.3% | ✅ usable |
| `LwrWsmSkidTurn` | 0.1% | ✅ usable |
| `LwrWheelProfile` | 30.8% | ⚠️ usable as 2-class profile (forward-fillable) |
| `LwrUpdatedOn` | 0.08% | ✅ usable |
| `LwrScheduleId` | 4.2% | ✅ usable (28 distinct schedule types) |
| `LwrLocoId` | 0% | ✅ |
| `LwrPurpose` | 10% | ⚠️ raw codes, multi-valued (`"5,9"`), needs mapping |

### Turning-event evidence (the label source)

WAP7 rows by `LwrTurningType`: **0=10,508, 1=9,618, 2=10,294, NULL=1,061, -1=118**.
→ ~19,900 turning events (types 1/2) across 828 WAP7 locos ≈ **24 turning events per loco**. Sufficient for a turning/label and a "days since turning" feature.
Sentinel dates: only **87 / 31,599** WAP7 rows pre-2000 (0.28%). ✅

### Identity link

`WheelSetMeasurements.wsmWRId` → `LocoWheelRegister.LwrId`:
- 198,590 distinct `wsmWRId`, **0 unmatched** (100%).
- 1,164,467 / 1,174,535 WSM rows have a `wsmWRId` (99.1%).

**Verdict: USE — this is the missing wheel-register master.** It provides turning events, skid flags, wheel profile, and schedule context at the wheelset grain, and links 1:1 to every wheel measurement.

---

## 2. WheelFormationTemplates (`dbo.WheelFormationTemplates`)

| Metric | Value |
| --- | --- |
| Rows | 556; 12 rows per loco type (48 types covered) |
| WAP7 (`LotId=9`) | **12 rows** = 6 wheelsets × 2 ends, mapping `WftWSPos`(1–6) + `WftEndType`(1/2) → `WftWheelPos`(1–12) |
| WSM mappability | 1,158,965 / 1,174,541 rows (98.7%) have both `wsmWheelSetPosition` and `wsmW1EndType` |

Join check (WAP7, WSPos=1): `wsmW1EndType=1 → WheelPos=1`, `=2 → WheelPos=2` — consistent.

**Verdict: USE — resolves the wheel-position and axle-position gaps.** Individual wheel (1–12) is derivable for 98.7% of measurements by joining WSM on `(wsmWheelSetPosition, wsmW1EndType)`.

---

## 3. PrevLocoWheelDetails (`dbo.PrevLocoWheelDetails`)

**Row count = 0.** Empty table.

**Verdict: DO NOT USE — dead end.** Ignore this candidate entirely.

---

## 4. Context sources (Zone / Division / Home Shed)

| Source | Rows | WAP7 coverage | Fill | Verdict |
| --- | ---: | ---: | --- | --- |
| `OnlineDefects_LogHistory` | 387,761 | **54,407 WAP7 rows** | Zone 99.5%, Div 99.9%, **Shed 99.9% null** | ✅ Zone/Div for WAP7; shed absent |
| `DailyOverdueLocoCount` | 352,627 | **98,370 WAP7 rows** | HomeShed **0% null** | ✅ Home shed |
| `Integ_icms_LocoCurrentLocation` | 5,012 | **826 WAP7 locos** | currentZone/Division present | ✅ snapshot zone/div |
| `Integ_pub_COA_slamlocoSchedule` | 216,600 | — | LOCOSHED 0% null | ✅ shed |
| `Integ_rtis_Locodevice` | 28,106 | — | shed 1.8% null | ✅ shed |
| `INTEG_FOIS_LocoLocation` | 10,270 | **2 WAP7 locos only** | FOISZone 0% null | ❌ WAP7 coverage still negligible |

**Verdict: Zone, Division and Home Shed ARE obtainable for the WAP7 cohort** — but **not from FOIS**. Use `OnlineDefects_LogHistory` (zone/div) + `DailyOverdueLocoCount` (home shed). The earlier "missing" claim came from restricting the search to FOIS.

---

## 5. Wheel age / provision date

| Source | Usable |
| --- | ---: |
| `WheelSetMeasurements.wsmProvDate` | only 35% (65.2% null/pre-2000) |
| `EquipmentMasterRegister.EmrDoM` (wheel-type rows) | only 9.3% usable |
| `LocoEquipmentsHistory` | provision 88.9% usable, removal 72.8% null |

**Verdict: STILL PARTIAL — wheel age is the one feature that stays weak.** Best proxy is `LocoEquipmentsHistory.LoehProvisionDate` (88.9% fill), but it is assignment-level, not manufacture-level.

---

## 6. Abnormal events

| Source | Rows | Fill |
| --- | ---: | --- |
| `AbnormalityRegister` | 283,393 | jobcard link 68.8% |
| `EquipmentFailureRegister` | 48,126 | `EfrAbnormality` 0% null |

**Verdict: USE** — both tables are populated and linkable.

---

## Summary verdict

| Feature | Status after validation |
| --- | --- |
| Wheel position / axle position | ✅ SOLVED via WheelFormationTemplates (98.7% mappable) |
| Turning flag / days since turning | ✅ SOLVED via LocoWheelRegister (~19.9K WAP7 turning events) |
| QR / wheel profile | ⚠️ PARTIAL — 2-class profile, 69% fill |
| Previous maintenance / schedule | ✅ SOLVED via LwrScheduleId + LocoHistory |
| Inspection count | ✅ SOLVED (derivable from WSM history per wsmWRId) |
| Zone / Division | ✅ SOLVED via OnlineDefects (54K WAP7 rows) |
| Home Shed | ✅ SOLVED via DailyOverdueLocoCount (0% null) |
| Abnormal events | ✅ SOLVED via AbnormalityRegister + EquipmentFailureRegister |
| **Wheel age** | ⚠️ **PARTIAL — remains the weak feature (35% usable)** |
| **Health index** | ❌ by design — engineered, not a source column |

**Dead ends:** `PrevLocoWheelDetails` (empty), `INTEG_FOIS_LocoLocation` (negligible WAP7 coverage).

**Conclusion:** the data needed to build the matrix exists and is populated. Only **wheel age** stays partial and **health index** stays deliberately blocked. Proceed to write extraction SQL for LocoWheelRegister + WheelFormationTemplates + the two context sources.

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

Comparing root wear at the measurement immediately *before* vs *at* a `wsmturning=1` measurement:

| cur_turn | n | avg root before | avg root at | avg root delta | avg dia delta |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 (no turn) | 875,007 | 1.69 | 1.77 | +0.08 | +4.08 |
| **1 (turn)** | 33,272 | **2.05** | **0.95** | **−1.10** | +3.00 |

At a turning-flagged measurement, root wear **drops by ~1.1 and resets to ~0.95** — consistent with a **cumulative-since-turning index** that resets. Diameter increases (+3mm) — consistent with reprofiling restoring the profile.

### 7.3 But root also DECREASES without any turning flag — contradicts pure cumulative

In intervals where both endpoints are `wsmturning=0` (856,547 intervals):

| outcome | n | pct |
| --- | ---: | ---: |
| root increased | 415,978 | **48.6%** |
| root decreased | 227,334 | **26.5%** |
| root unchanged | 213,235 | 24.9% |

If root wear were strictly cumulative, it should **never** decrease between turnings. 26.5% decrease contradicts that. Two possible explanations, both unconfirmed:
1. Unflagged turning/replacement events (the flag is incomplete), or
2. Root wear is a **direct measurement** with noise / remeasurement variance, not a cumulative index.

### 7.4 Deeper split — root drops without a flag look like measurements, not turnings

| root bucket (non-turn intervals) | n | avg dia delta | dia increased | dia decreased |
| --- | ---: | ---: | ---: | ---: |
| root drop > 1.0 | 118,143 | **−2.14** | 14,887 | 95,264 |
| root drop 0.1–1.0 | 103,985 | −0.13 | 14,041 | 59,010 |
| root drop < 0.1 | 215,542 | −0.17 | 12,537 | 80,161 |
| root gain > 0.1 | 405,085 | −0.45 | 30,713 | 189,774 |

Large root drops (without a turning flag) come with **diameter DECREASING** (−2.14), not increasing. A real reprofiling turn would show diameter *increasing*. So big unflagged root drops look like **measurement resets / wheel replacement / noise**, not turning.

### 7.5 LocoWheelRegister remark text — what LwrTurningType really encodes

| LwrTurningType | mentions turning/reprofil | mentions done/completed | n |
| ---: | ---: | ---: | ---: |
| 0 | 8,035 | 7,194 | 44,744 |
| 1 | 9,252 | 25,548 | 47,501 |
| 2 | 5,263 | 15,312 | 81,962 |

Remark samples: type=1 → `"Bogie no.1 requierd wrp due to flange wear, root wear excess"`, `"TFRW DONE."`; type=2 → `"All parameters are within permissible limit"`, `"TT Not required, all wheels are regular checked."`. This suggests `LwrTurningType` may encode a **turning-required/recommendation outcome**, not a completed-turning event with an exact timestamp. That is unconfirmed.

### 7.6 Verdict — semantics are UNRESOLVED

- **Root wear:** the turning-reset evidence (7.2) suggests cumulative-since-turning, but the 26.5% no-flag decreases (7.3) and the decreasing-diameter big drops (7.4) are incompatible with a clean cumulative index. **Not confirmed.**
- **Turning flag:** `wsmturning` and `LwrTurningType` disagree (7.1); `LwrTurningType` likely encodes a recommendation, not an event (7.5). **Not confirmed.**

**Consequence for modelling:** do **not** compute a turning-reset, `days_since_turning`, or a cumulative root-wear feature yet. A regression target built by *assuming* reset semantics will silently encode an unverified assumption. These two fields need a domain-owner decision (same list as `degradation_semantics.md` §10.3 and §10.6) before they can feed the feature store.

### Evidence queries

Ad-hoc T-SQL against live DB, 2026-08-03 (temp workspace `opencode/semantics*.py`).

## Evidence queries

Ad-hoc profiling run against the live DB on 2026-08-03; SQL in temp workspace `opencode/validate_new_tables*.py`.
