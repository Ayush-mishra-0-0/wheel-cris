# Domain-owner questions — wheel turning & root-wear semantics (v2, owner-confirmed)

> All questions from v1 answered by the rolling-stock/engineering owner on 2026-08-03.
> Q2 was re-validated from all angles against the data (this file records the evidence).
> Everything in matrix section C14/C15 that depends on these answers is now unblocked.
> Materialised 2026-08-03: `turning_indicator_raw` and `days_since_turning` released into
> Feature Store v1.0 (spec v1.1 for `wheel_age_days_proxy`); see candidate matrix C14/C15/C21.

## Q1 — What does `wsmturning = 1` mean? ✅ CONFIRMED

**Owner answer:** `wsmturning=1` records **"reprofiling/turning performed at or near this
measurement"** — an event flag at the measurement, not a cumulative "has been turned" state.

**Consequence:** `days_since_turning` can be built from `wsmturning` events on
`wsmEquipmentId` (identity confirmed in Q7). Marked RESOLVED.

## Q2 — Is the `wsmturning` flag exhaustive? ✅ RE-VALIDATED (root is NOT cumulative)

**Owner challenge:** *"can't the wheel be of other build or went through some other route or
some feature might have affected? validate this question from all angles first."*

**Re-validation (all angles, 2026-08-03, full 1.17M-row measurements):**

| Angle | Evidence | Reading |
| --- | --- | --- |
| Is root cumulative? | On 64,729 equipment with ≥6 measurements, **38.8% of root changes are decreases** and there are **420,487 up→down flips**. A cumulative index would be monotonic between resets. | **Root is a direct measured depth with variance, NOT cumulative.** |
| What resets root to ~0? | 150,729 root-reset rows (`wsmRoot1 ≤ 0.2`): **73.8% coincide with a `wsmProvDia` change** (replacement/new wheel); only 7.5% are flagged turning. | Root ~0 = **replacement**, not turning. |
| The old "26.5% unflagged root-decrease" | 268,145 unflagged root decreases; **77.1% have a provision-date change** (replacement). After excluding provision-changes + root-resets, only **13.6% (≈26,750)** remain with root drop >0.5. | The 26.5% figure was inflated by replacements + direct-depth variance. |
| Residual (~26,750) | Median diameter change 5.5 mm, 84% diameter-decreased, no provision change, no reset. | A genuine residual that still *looks* like turning (diameter cut) — the flag may undercount turnings slightly. |
| At flagged turning rows | Root decreases only 61.9% (mean 1.06), and 24% actually *increase*; diameter drops ~2.8 mm median. | Consistent with reprofiling removing material (Q5), root not reset to 0. |

**Conclusion:** the flag-exhaustiveness concern is materially reduced. Root is a **direct
measured depth** (variance + resets only at replacement), so the 26.5% figure was mostly
replacement/variance, not missed turnings. A small residual (~26,750 rows, ~0.6% of pairs)
still carries a turning-like signature, so `days_since_turning` may slightly undercount
events — acceptable for a feature, not acceptable as a "true turning count" label.

## Q3 — What does `LwrTurningType` in `LocoWheelRegister` really mean? ✅ CONFIRMED

**Owner answer:** `LwrTurningType` is a **post-turning inspection outcome**, not a completed
turning event and not a recommendation for future work.

**Consequence:** it must NOT contribute to turning counts or `days_since_turning`. Only
`wsmturning` in `WheelSetMeasurements` is the event signal (per Q1/Q2).

## Q4 — Root wear: cumulative or direct measured depth? ✅ RESOLVED (direct measured depth)

The Q2 re-validation answers this: **`wsmRoot` is a direct measured root/fillet dimension
with measurement variance**. It resets to ~0 only when a wheel is replaced (provision change),
not at turning. No regression target may assume cumulative-since-turning semantics.

## Q5 — Diameter decreases at turning — semantics doc corrected ✅ CONFIRMED

**Owner answer:** *"yes at each turning, wheel is cut so dia will decrease"* — reprofiling
removes material → **smaller diameter**.

**Consequence:** `degradation_semantics.md` §3.1 is corrected (turning *decreases* diameter).
The sign convention for `diameter_delta_raw_mm` (negative = loss at turning) is confirmed.

## Q6 — Wheel age: which date is authoritative? ✅ ANSWERED (manufacture/in-service)

**Owner question:** *"which field sounds most genuine — wheel manufacturing should be its real
date."* Re-framed as: **which field is the authoritative wheel-in-service (provision) date for
calculating wheel age?**

**Evidence (2026-08-03, per measured wheelset, `wsmEquipmentId` = `EmrId`):**

| Field | Usable | Note |
| --- | ---: | --- |
| `EquipmentMasterRegister.EmrDoM` (manufacture) | 11.9% | The genuine "real" wheel date, but sparse. |
| `EquipmentMasterRegister.EmrDoR` (in-service/DoR) | **58.4%** | ≈ `EmrDoM` (median 4 days apart; 52.8% same month) → best usable **manufacture-equivalent** date. |
| `EquipmentMasterRegister.EmrDoC` (commission) | 41.0% | Aligned to DoR/DoM. |
| `WheelSetMeasurements.wsmProvDate` | 35.0% | Lags manufacture by ~94 days median (stock time before fitting) → a *fit* date, not manufacture. |
| `LocoEquipmentChangeRegister.LerProvidedOn` | loco-level only | Only 9.5% of measured wheelsets directly link; it is a **locomotive-position provision** record, not per-wheel. |
| `LocoEquipmentsHistory.LoehProvisionDate` | 88.9% | History ledger; provision-on-loco, not manufacture. |

**Recommendation:** use **`EmrDoR` (in-service ≈ manufacture)** as the authoritative wheel
age origin when populated, falling back to `EmrDoM`, then `wsmProvDate` as the provision/fit
date. `LerProvidedOn`/`LoehProvisionDate` are loco-level proxies only and must not be used as
per-wheel manufacture dates. Coverage will be ~58% (EmrDoR) — a wheel-age feature must carry a
"date source" column so missing vs provision-proxy ages are distinguishable.

## Q7 — Does turning preserve wheel identity? ✅ RESOLVED

- `wsmEquipmentId` = `EquipmentMasterRegister.EmrId` (100% match) is the stable per-wheelset
  identity; the interval pipeline already keys on it.
- `wsmWRId` is a per-measurement register reference (changes 99.8% between rows; 97.7% reused
  across locos) — NOT a wheel identity.
- Turning preserves identity at the equipment level (7,368 equipment with ≥2 turnings on the
  same id). Register join `wsmWRId = LwrId` matches 99.98% of WAP7 interval endpoints.

---

**Status:** all seven questions closed. No further domain-owner input is required to build the
turning (`days_since_turning`), root-wear (direct-depth), diameter (decrease-at-turning) and
wheel-age (EmrDoR-anchored) features.
