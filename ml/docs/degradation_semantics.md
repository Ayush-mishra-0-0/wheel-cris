# Engineering Degradation Semantics

## Purpose

This document defines how wheel measurements represent physical degradation. It is the first engineering-decision artifact: before we calculate health scores, wear rates, or maintenance priority, we must agree what each measurement means, which direction indicates material loss, and how turning or replacement resets history.

**Status:** draft pending domain-owner review. Items marked **requires rolling-stock engineering confirmation** cannot be released as features until confirmed.

**Evidence base:** Silver `wheel_measurements` dataset (1,165,641 records; ~1,031,574 consecutive equipment-level pairs with `wsmEquipmentId` continuity).

---

## Scope

- Source: `WheelSetMeasurements` table (Bronze/Silver `wheel_measurements`).
- Grain: one measurement event, and the interval between two attributable measurements.
- Boundary: this document defines semantics only. It does not release distance-based wear rates, ML labels, or health scores. Those remain gated on the rules defined here.

---

## 1. Measurement Inventory and Degradation Questions

The engineering question between two inspections is:

> How did the wheel geometry change, and is that change consistent with expected material loss, measurement noise, or maintenance?

Measurable dimensions in the source:

| Side | Diameter | Flange (0–4) | Root | Tread/Thread | Wheel Gauge | Flange Thickness | Tire Thickness | Axle Dia |
|------|----------|--------------|------|--------------|-------------|------------------|----------------|----------|
| Side 1 | `wsmDia1` | `wsmFlange1` | `wsmRoot1` | `wsmThread1` | `wsmWheelGauge1` | `wsmFlangeThickness1` | `wsmTireThikness1` | `wsmAxelDia1` |
| Side 2 | `wsmDia2` | `wsmFlange2` | `wsmRoot2` | `wsmThread2` | `wsmWheelGauge2` | `wsmFlangeThickness2` | `wsmTireThikness2` | `wsmAxelDia2` |

Other fields are metadata (identity, timestamps, turning flags, prior values) or derived source columns (`wsmWear`, `wsmWearRate`, etc.) whose meaning must be confirmed before use.

---

## 2. Sign Convention

A unified sign convention makes every degradation feature consistent:

| Term | Meaning | Mathematical convention |
|------|---------|---------------------------|
| **Wear / material loss** | Material removed from the wheel | **Positive** |
| **Material gain / build-up** | Material added (turning deposit, remetalling, measurement artefact) | **Negative** |
| **No change** | Same measurement at both endpoints | Zero |

For direct wear dimensions that **decrease** with wear (diameter, flange thickness, tire thickness):

```text
degradation_delta = start_value - end_value
```

For profile dimensions that **increase** with wear (root wear depth, flange height, hollow tread):

```text
degradation_delta = end_value - start_value
```

**Requires confirmation:** which measurements increase versus decrease with genuine wear.

---

## 3. Measurement-by-Measurement Semantics

### Legend

| Field | Meaning |
|-------|---------|
| `Physical Meaning` | What the dimension represents on the wheel |
| `Expected Degradation Direction` | Whether the raw value increases (+) or decreases (-) with wear |
| `Observed Delta Evidence` | Statistical evidence from ~1M consecutive equipment-level intervals |
| `Possible Intervention Effects` | How turning, reprofiling, replacement affect the value |
| `Required Engineering Confirmations` | Questions that need domain-owner sign-off |
| `Safe Derived Calculations` | What can be computed now |
| `Unsafe/Blocked Calculations` | What must not be computed until confirmations |
| `Dependencies Before Feature Release` | Gates in `configs/engineering_feature_specification_v1.json` |

---

### 3.1 Wheel Diameter (`wsmDia1`, `wsmDia2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Wheel tread diameter at the measurement plane (mm). |
| **Expected Degradation Direction** | **Decreases** with wear (material removed from tread). |
| **Observed Delta Evidence** | n=1,031,574 intervals. **Negative** (decrease): 51.26%. **Positive** (increase): 9.13%. **Zero**: 39.61%. |
| **Possible Intervention Effects** | Turning/reprofiling **decreases** diameter — material is cut away from the tread to restore the profile (owner-confirmed 2026-08-03; diameter drops ~2.8 mm median at turning rows, ~3.7 mm at 91% of turning rows). Wheel replacement resets to new-wheel diameter. |
| **Required Engineering Confirmations** | 1. Unit is millimetres (data clusters 1055–1090, consistent with Indian locomotive wheels). 2. Measurement plane repeatability across inspections. 3. `wsmProvDia1/2` = provision/new diameter reference. 4. Condemning limit for diameter. |
| **Safe Derived Calculations** | Raw delta (`start - end`) as **unsigned material-loss signal** for intervals **without turning flags**. Quarantine values outside [600, 1300] mm. |
| **Unsafe/Blocked Calculations** | Wear rate (mm/day or mm/km) — blocked on distance semantics and turning reset rule. Health score — blocked on approved geometry limits. |
| **Dependencies Before Release** | `wear_rate_mm_per_day` requires: (a) approved wear dimensions, (b) turning reset rule, (c) unit confirmation. `interval_distance_km` must be released for mm/km rate. |

---

### 3.2 Flange Height / `wsmFlange1`, `wsmFlange2` (0–4 range)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | **Unclear** — possibly flange height, a coded condition score, or legacy field. Values 0–4 with outliers to 1596. |
| **Expected Degradation Direction** | **Requires confirmation**. If flange height: increases with wear. If condition score: meaning unknown. |
| **Observed Delta Evidence** | n=1,031,586. **Positive**: 34.06%. **Negative**: 26.65%. **Zero**: 39.29%. Mixed signal — not a clean wear monotonic trend. |
| **Possible Intervention Effects** | If flange height: turning restores profile. If condition score: may reset or change per inspection rubric. |
| **Required Engineering Confirmations** | 1. Is this flange height, a condition code, or a legacy measurement? 2. If flange height, what is the unit (mm? coded?) and measurement method. 3. Relationship to `wsmFlangeThickness1/2` (28–32 mm range). |
| **Safe Derived Calculations** | **None** — blocked until semantics confirmed. |
| **Unsafe/Blocked Calculations** | Any differencing, wear rate, or health contribution. |
| **Dependencies Before Release** | All degradation features blocked until domain owner defines field meaning. |

---

### 3.3 Root Wear (`wsmRoot1`, `wsmRoot2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Wear at the wheel-root/fillet area. **RESOLVED (2026-08-03): direct measured depth/width with measurement variance — NOT a cumulative since-turning index.** Evidence: 38.8% of root changes on 64,729 long-history equipment are decreases (420,487 up→down flips); root resets to ~0 at provision changes (73.8%) = replacement, only 7.5% at flagged turning. **RESOLVED (2026-08-08, Q8): direct defect-severity measurement; 3 mm = maximum/condemning value, lower is better.** **SUPERSEDED ON LIMIT (2026-08-19): Wrpld table = authoritative wear register → root condemning = 6.0 mm** (`configs/limit_register_v1.json`). |
| **Expected Degradation Direction** | **Increases** with wear (root radius deepens/width grows); noisy, may decrease on re-measurement. |
| **Observed Delta Evidence** | n=1,031,482. **Positive** (increase): 45.24%. **Negative**: 28.50%. **Zero**: 26.26%. Predominantly increasing; the negative tail is measurement variance + replacement resets, not cumulative resets. |
| **Possible Intervention Effects** | Turning reduces root only modestly (~1.0, and in 24% of cases root *increases* at turning rows — direct-depth noise). **Replacement resets root to ~0.** |
| **Required Engineering Confirmations** | 1. Unit is mm (confirmed 2026-08-08). 2. Condemning/limit value = **3 mm** (confirmed 2026-08-08); lower is better; root > 3 mm = beyond condemning. **SUPERSEDED 2026-08-19: Wrpld table sets root wear 0-6 mm → condemning value is now 6.0 mm** (`configs/limit_register_v1.json`). (Direct-vs-cumulative resolved.) |
| **Safe Derived Calculations** | Raw delta (`end - start`) as **direct root-depth change**; treat replacement resets (provision-change) as boundaries, not wear. **Margin-to-condemning now computable:** `root_margin = 6.0 - wsmRoot` (negative = beyond condemning) per the approved Wrpld register. |
| **Unsafe/Blocked Calculations** | Wear rate per distance. Any cumulative-since-turning index. |
| **Dependencies Before Release** | `wear_rate_mm_per_day` blocked on (a) approved wear dimensions, (b) turning reset rule. |

---

### 3.4 Tread / Hollow Tread (`wsmThread1`, `wsmThread2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Tread defect/hollow depth. **RESOLVED (2026-08-08, Q8): direct defect-severity measurement; 3 mm = maximum/condemning value, lower is better.** **SUPERSEDED ON LIMIT (2026-08-19): Wrpld table = authoritative wear register → tread condemning = 6.5 mm** (`configs/limit_register_v1.json`). Field name `wsmThread` = "tread". |
| **Expected Degradation Direction** | **Increases** with wear (hollow tread deepens with wear). |
| **Observed Delta Evidence** | n=1,031,566. **Positive**: 30.70%. **Negative**: 18.80%. **Zero**: 50.50%. High zero rate suggests many inspections don't record this or it's not always applicable. |
| **Possible Intervention Effects** | Turning/restores tread profile → should reduce hollow measurement. |
| **Required Engineering Confirmations** | 1. Exact physical meaning — **RESOLVED: tread defect/hollow depth (Q8)**. 2. Unit — mm (confirmed 2026-08-08). 3. Wear direction — **increases with wear (Q8)**. 4. Whether recorded for all wheel types or only specific profiles — open. |
| **Safe Derived Calculations** | **Margin-to-condemning now computable:** `tread_margin = 6.5 - wsmThread` (negative = beyond condemning) per the approved Wrpld register (was 3.0 mm in Q8; superseded 2026-08-19). |
| **Unsafe/Blocked Calculations** | Wear rate per distance; health contribution until limits cross-validated across fleet. |
| **Dependencies Before Release** | Feature release now gated only on remaining per-type applicability confirmation (Q8). |

---

### 3.5 Wheel Gauge / Back-to-Back (`wsmWheelGauge1`, `wsmWheelGauge2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Back-to-back distance across the wheelset (or wheel-pair). Assembly-level attribute, not single-wheel material loss. |
| **Expected Degradation Direction** | Not a single-wheel wear dimension. May drift due to axle wear, bearing wear, or measurement setup. |
| **Observed Delta Evidence** | n=1,030,795. **Positive**: 21.24%. **Negative**: 19.24%. **Zero**: 59.52%. Nearly symmetric, high zero rate — not a clean wear signal. |
| **Possible Intervention Effects** | Wheel turning does **not** reset gauge (it's an assembly property). Wheelset replacement or axle work may change it. |
| **Required Engineering Confirmations** | 1. Confirm this is back-to-back gauge (standard ~1596 mm for Indian broad gauge). 2. Confirm it is per-wheelset, not per-wheel. 3. Condemning limits. |
| **Safe Derived Calculations** | Track as **wheelset condition feature** (not single-wheel wear). Flag large changes as possible measurement error or assembly intervention. |
| **Unsafe/Blocked Calculations** | Single-wheel wear rate. Tread wear proxy. |
| **Dependencies Before Release** | Not a degradation feature for wheel health index. Can be a separate "wheelset geometry" feature if confirmed. |

---

### 3.6 Flange Thickness (`wsmFlangeThickness1`, `wsmFlangeThickness2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Thickness of the wheel flange (mm). Primary flange-wear dimension. |
| **Expected Degradation Direction** | **Decreases** with wear (flange tip/thickness wears away). |
| **Observed Delta Evidence** | n=1,024,294. **Negative** (decrease): 30.57%. **Positive** (increase): 25.62%. **Zero**: 43.82%. Net decreasing trend, consistent with wear. Positive deltas likely turning/reprofiling or measurement noise. |
| **Possible Intervention Effects** | Turning/reprofiling **increases** flange thickness (restores profile). Replacement resets to new. |
| **Required Engineering Confirmations** | 1. Unit is mm (values 28–32 mm typical). 2. Relationship to `wsmFlange1/2` (0–4 range) — same dimension different encoding, or different physical measurement? 3. `OldwsmFlange1/2` legacy field meaning. 4. Condemning limit for flange thickness. |
| **Safe Derived Calculations** | Raw delta (`start - end`) as **unsigned material-loss signal** for intervals without turning flags. Quarantine outside [10, 50] mm. |
| **Unsafe/Blocked Calculations** | Wear rate per distance (blocked on distance + turning reset). Health score (blocked on limits). |
| **Dependencies Before Release** | `wear_rate_mm_per_day` requires: (a) approved wear dimensions, (b) turning reset rule, (c) unit confirmation. |

---

### 3.7 Tire Thickness (`wsmTireThikness1`, `wsmTireThikness2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Remaining tire thickness on the wheel centre (mm). |
| **Expected Degradation Direction** | **Decreases** with wear. |
| **Observed Delta Evidence** | n=1,016,039. **Negative** (decrease): 47.42%. **Positive**: 8.32%. **Zero**: 44.27%. Strong decreasing signal — consistent with tire wear. |
| **Possible Intervention Effects** | Turning/reprofiling removes worn surface → **decreases** tire thickness further (exposes deeper material) or resets depending on measurement convention. **Requires confirmation**: does turning increase or decrease the recorded tire thickness? |
| **Required Engineering Confirmations** | 1. Unit is mm (values 40–50 typical, max 71). 2. Measurement convention: is this remaining rubber/tire thickness from tread surface inward? 3. Turning effect: does reprofiling reduce recorded tire thickness (material removed) or is it a "remaining to condemning" measure that increases? 4. Independence from diameter — diameter reduction and tire thickness reduction are mechanically coupled; do not double-count. 5. Condemning limit. |
| **Safe Derived Calculations** | Raw delta (`start - end`) as material-loss signal for intervals without turning flags. Quarantine outside [5, 100] mm. |
| **Unsafe/Blocked Calculations** | Wear rate per distance. Health score. Using both diameter and tire thickness as independent wear signals without validation. |
| **Dependencies Before Release** | Same as flange thickness. Additionally: confirm mechanical coupling with diameter to avoid double-counting. |

---

### 3.8 Axle Diameter (`wsmAxelDia1`, `wsmAxelDia2`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Axle journal or body diameter. Separate component. |
| **Expected Degradation Direction** | Not a wheel-tread wear signal. |
| **Observed Delta Evidence** | n=998,460. **Zero**: 99.78%. **Positive**: 0.09%. **Negative**: 0.14%. Essentially constant — confirms it is not a wheel wear dimension. |
| **Possible Intervention Effects** | Axle turning/grinding or replacement would change it. |
| **Required Engineering Confirmations** | None for wheel degradation — exclude from wheel health. |
| **Safe Derived Calculations** | None for wheel degradation. Can be a separate "axle condition" feature if needed. |
| **Unsafe/Blocked Calculations** | Any wheel wear or health calculation. |
| **Dependencies Before Release** | N/A — excluded from wheel degradation layer. |

---

### 3.9 Road Gauge / K-Value / S-Distance (`wsmRoadGuage1–6`, `wsmKvalue1`, `wsmSDistance1`)

| Attribute | Value |
|-----------|-------|
| **Physical Meaning** | Unknown. Likely track/rail-side references or derived geometric parameters. Not wheel measurements. |
| **Expected Degradation Direction** | N/A for wheel wear. |
| **Observed Delta Evidence** | Not computed — fields sparsely populated or unclear meaning. |
| **Possible Intervention Effects** | N/A. |
| **Required Engineering Confirmations** | 1. Physical meaning of each field. 2. Whether any relate to wheel profile (QR, flange profile parameters). |
| **Safe Derived Calculations** | **None** — blocked until semantics confirmed. |
| **Unsafe/Blocked Calculations** | Any differencing for wheel degradation. |
| **Dependencies Before Release** | All blocked. |

---

### 3.10 Derived Source Columns (Pre-computed in Source)

| Field | Observed Range | Evidence | Status |
|-------|----------------|----------|--------|
| `wsmWear` | -1,019,325 to +1,019,333; mean ~ -6 | Extreme range indicates sentinel values, mixed units, or mixed conventions (since-new? since-turning?). | **Blocked** — do not use as label or feature until formula confirmed. |
| `wsmWear2` | -106,023 to +106,057 | Same concern. | **Blocked** |
| `wsmWearRate` | -1,019,326 to +11,853 | Pre-computed rate. Unknown denominator (days? km? per inspection?). | **Blocked** |
| `wsmWearRate2` | -1,060,240 to +9,679 | Same. | **Blocked** |
| `WsmFlWearRate1/2` | Small deltas ±30 with outliers | Pre-computed flange wear rate. Unknown sign convention. | **Blocked** |
| `WsmRtWearRate1/2` | Mostly negative | Pre-computed root wear rate. Direction unknown. | **Blocked** |

**Principle:** Do not ingest pre-computed wear values into the Engineering Layer until their exact formula, denominator, sign convention, and handling of turning are documented and approved. They may encode legacy business rules no longer valid.

---

## 4. Turning and Reprofiling Semantics

### Observed Fields

| Field | Type | Values | Null Rate |
|-------|------|--------|-----------|
| `wsmturning1` | float | 0, 1 | ~2% |
| `wsmturning2` | float | 0, 1 | ~2.7% |
| `wsmSkidTurn1` | string | "0", "1", "--", "" | ~1.4% |
| `wsmSkidTurn2` | string | "0", "1", "--", "" | ~1.7% |

### Required Decisions from Domain Owner

1. **What does `wsmturning1 = 1` mean?**
   - Wheel turned/reprofiled **at this measurement**?
   - Wheel **previously** turned?
   - Skid/flat detected and turned?

2. **Relationship between `wsmturning1/2` and `wsmSkidTurn1/2`?**
   - Subset? Different workflows? Different data-entry systems?

3. **Does turning reset a wheel to "as-new" or to a known turned profile?**
   - Diameter restored by amount removed.
   - Flange profile restored.
   - Root/tread/hollow measurements reset.

4. **Minimum restored diameter / flange thickness after turning?**
   - Needed for wear-budget and health-index calculations.

5. **Is the same physical wheel retained after turning, or is it a replacement with new identity?**
   - Affects whether `wsmEquipmentId` is a persistent wheel identifier or a wheelset-position identifier.

### Recommended Handling Until Confirmed

- Treat any measurement with `wsmturning1/2 = 1` or `wsmSkidTurn1/2 != "0"` as a **suspected state-change event**.
- Do not calculate wear across an interval containing a turning event at either endpoint until the reset rule is approved.
- Retain all raw values and flags; do not impute or silently adjust.

---

## 5. Measurement Independence

| Dimension | Independent Wear Signal? | Notes |
|-----------|------------------------|-------|
| Diameter | Yes (primary) | Direct measure of tread material. |
| Tire thickness | Partially | Related to diameter depending on convention. |
| Flange thickness | Yes | Independent flange-wear signal. |
| Flange height (wsmFlange1/2) | To be confirmed | May be derived from flange thickness. |
| Root wear | To be confirmed | Could be related to tread and flange geometry. |
| Tread/hollow | To be confirmed | Related to diameter wear. |
| Wheel gauge | **No** for single-wheel wear | Wheelset assembly attribute. |
| Axle diameter | **No** | Different component. |

**Rule:** If two dimensions are mechanically coupled (diameter ↔ tire thickness, flange height ↔ flange thickness), they must not both be treated as independent predictors in a health index without engineering confirmation. Choose one primary dimension per wear mode.

---

## 6. Measurements That Must Never Be Differenced for Degradation

1. `wsmWheelGauge1/2` — wheelset/assembly attribute, not single-wheel material loss.
2. `wsmAxelDia1/2` — axle attribute.
3. `wsmRoadGuage1–6` — track/road reference; meaning unknown.
4. `wsmKvalue1`, `wsmSDistance1` — meaning unknown.
5. `wsmStatus`, `wsmWheelAnalysisFlag`, `wsmW1EndType`, `wsmWheelSetPosition`, `WsmPosition` — categorical, not continuous measurements.
6. Identity/linkage fields (`wsmId`, `wsmEquipmentId`, `wsmWRId`, `wsmRSId`, etc.).
7. Any pre-computed `wsmWear*`, `*WearRate*` columns until formula approved.

---

## 7. Sentinel and Impossible Values — Observed Evidence

| Field | Observed Issue | Required Action |
|-------|---------------|-----------------|
| Diameter fields | Max ~1,020,352 mm; zero values | Quarantine outside plausible locomotive wheel range. |
| Flange fields | Max 1,596; negative values | Same. |
| Root fields | Max 41,595 | Same. |
| Wheel gauge | Max ~1,569,615 | Same. |
| Tire thickness | Max 509,695 | Same. |
| `WsmPrvUpdatedOn` | `1900-01-01` sentinel date | Treat as missing previous timestamp. |
| `wsmDateDiff` | Negative values (-1,546 to 3,769) | Investigate out-of-order inspections; do not use raw without temporal integrity check. |

**Draft plausible-range table (requires engineering approval):**

| Dimension | Expected Normal Range (mm) | Hard Quarantine Lower | Hard Quarantine Upper |
|-----------|---------------------------|----------------------|----------------------|
| Wheel diameter | 900–1,250 | 600 | 1,300 |
| Flange thickness | 20–40 | 10 | 50 |
| Tire thickness | 20–90 | 5 | 100 |
| Wheel gauge | 1,350–1,650 | 1,300 | 1,700 |
| Root / Tread | 0–15 | 0 | 30 |

---

## 8. Interval Delta Rules

For a valid engineering interval (same `wsmEquipmentId`, same locomotive, positive duration, Gold-B assignment):

1. **Compute raw deltas only for confirmed direct dimensions** (diameter, flange thickness, tire thickness).
2. **Identify state-change intervals:** mark any interval where `wsmturning1/2 = 1` or `wsmSkidTurn1/2 != "0"` at start or end as a maintenance/reset boundary.
3. **Exclude or reset intervals across turning** until a reset rule is approved.
4. **Do not compute wear rate** until a distance or time normalization is released.
5. **Retain sign and magnitude** for every delta for audit; never silently flip signs to hide negative wear.

---

## 9. Release Gating — Features Blocked Until Confirmations Resolved

| Feature (in `engineering_feature_specification_v1.json`) | Blocked Until |
|---------------------------------------------------------|---------------|
| `wear_rate_mm_per_day` | (a) Approved wear dimensions, (b) Turning reset rule, (c) Unit confirmation |
| `wear_rate_mm_per_km` | Above + `interval_distance_km` released |
| `wheel_health_index` | Above + geometry limits + health rule design |
| `turning_indicator_raw` | Turning-flag business semantics confirmed |
| `diameter_delta_raw_mm` | **READY_WITH_CAVEAT** — released as raw delta; not labelled as wear until units/turning confirmed |

---

## 10. Open Questions for Domain Owners

1. **Units & measurement plane:** Confirm diameter, flange thickness, tire thickness are in mm. Confirm measurement plane repeatability.
2. **`wsmFlange1/2` vs `wsmFlangeThickness1/2`:** Same field at different system generations? Different physical measurements?
3. **`wsmRoot1/2`:** **RESOLVED (Q8, 2026-08-08): direct measured defect depth, 3 mm = max/condemning, lower is better.** (Direct-vs-cumulative resolved 2026-08-03.)
4. **`wsmThread1/2`:** **RESOLVED (Q8, 2026-08-08): direct tread defect/hollow depth, 3 mm = max/condemning, lower is better.** Open: per-type applicability.
5. **`wsmWheelGauge1/2`:** Confirm back-to-back gauge per wheelset. Condemning limits?
6. **Turning flags:** Precise meaning of `wsmturning1/2` and `wsmSkidTurn1/2`. Reset rule for all wear dimensions.
7. **Pre-computed wear fields:** Source formulas for `wsmWear`, `wsmWearRate`, `WsmFlWearRate*`, `WsmRtWearRate*`.
8. **Plausible ranges & condemning limits:** Approved engineering limits for each dimension.

---

## 11. References

- `docs/data_dictionary/wheel_measurements.md` — full column profile
- `docs/data_dictionary/wheel_measurements_sample.md` — sample profile
- `validation/engineering_truth_validation.md` — measurement integrity checks
- `configs/engineering_feature_specification_v1.json` — feature release gates
- `docs/rtis_distance_semantics.md` — distance semantics (blocks mm/km rates)
- `docs/distance_recovery_plan.md` — distance source alternatives

---

## 12. Change Log

| Date | Version | Change |
|------|---------|--------|
| 2026-07-29 | 1.0 | Initial version with observed delta statistics from Silver data (n≈1M intervals). |
| 2026-08-08 | 1.1 | §3.3/§3.4: `wsmRoot1/2` and `wsmThread1/2` semantics confirmed (Q8) — direct defect depth, 3 mm max/condemning, lower is better. Root/tread margin-to-condemning unblocked. |