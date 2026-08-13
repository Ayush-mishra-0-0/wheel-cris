# Wheel Engineering State Specification v1.0

**Status:** FROZEN — Approved as versioned engineering contract v1.0 (2026-08-06). This document is immutable; any change requires a new semantic version, never an in-place edit.
**Grain:** One attributable inspection measurement at its measurement timestamp.
**Purpose:** Represent what was measured about a wheel/wheelset and its point-in-time context. This is not a health score, an engineering-need label, or a maintenance recommendation.
**Versioned release:** `wheel_engineering_state_v1.0` (`model_datasets/v3/`), governed by `wheel_engineering_state_manifest_v1.0.json`.

## 0. Immutability and versioning contract

- `wheel_engineering_state_v1.0` is treated as immutable **engineering truth**.
- Future features (track geometry, weather, physics-informed margins, telemetry)
  must **extend** the contract via new minor/major versions, never by mutating v1.0
  in place.
- A change that alters the meaning of an existing field, quality code, blocked field,
  or identity contract is a **minor** semantic change that requires a new dataset
  version and manifest. A change that alters the grain, identity, or the list of
  measured vs blocked states is a **major** contract change.
- Downstream artifacts must record which engineering-state version they consume.

## 1. Output contract

Every state record contains four groups:

1. **Identity and time:** stable wheelset identity, measurement identifier, measurement timestamp, attributable locomotive/context identifiers, and source quality tier.
2. **Measured engineering state:** raw source values preserved side-by-side with per-field validity flags.
3. **Observed maintenance context:** prior recorded turning/replacement indicators only; never a post-measurement action field.
4. **Point-in-time operating context:** only released RTIS/FOIS/maintenance-context features available at the measurement timestamp.

The state must preserve unknowns. Missing, semantically blocked, and physically implausible values are distinct states and must not be silently median-imputed in the engineering-state dataset.

## 2. Measurement inventory

| State component | Source fields | Status | Permitted interpretation |
| --- | --- | --- | --- |
| Tread diameter | `wsmDia1`, `wsmDia2` | Measured, quality-gated | Current measured diameter. |
| Flange thickness | `wsmFlangeThickness1`, `wsmFlangeThickness2` | Measured, quality-gated | Current measured flange thickness. |
| Root / fillet | `wsmRoot1`, `wsmRoot2` | Measured, quality-gated | Direct measured root/fillet value; noisy and not cumulative. |
| Tire thickness | `wsmTireThikness1`, `wsmTireThikness2` | Measured, quality-gated | Current recorded tire-thickness value; do not independently aggregate with diameter. |
| Wheel gauge | `wsmWheelGauge1`, `wsmWheelGauge2` | Measured wheelset context | Wheelset assembly geometry, not single-wheel material wear. |
| Flange field | `wsmFlange1`, `wsmFlange2` | Semantics blocked | Preserve raw field only. Do not call it flange height or calculate a margin. |
| Tread/thread field | `wsmThread1`, `wsmThread2` | Semantics blocked | Preserve raw field only. Do not call it hollow tread or calculate a margin. |
| QR/profile parameters | `wsmKvalue1`, `wsmSDistance1` | Semantics blocked | Preserve raw field only. QR relationship is unconfirmed. |
| Turning / skid record | `wsmturning1/2`, `wsmSkidTurn1/2` | Observed event context | Recorded maintenance/action context; not engineering need. |

The source profile is recorded in [engineering_state_profile_report.md](../models/experiments/v3/engineering_state_profile/engineering_state_profile_report.md). Its plausibility windows are quality filters, not condemning limits.

## 3. Quality-state encoding

Each usable measurement must have a companion quality code:

| Code | Meaning | Consumer rule |
| --- | --- | --- |
| `OBSERVED_VALID` | Present and within the documented plausibility window. | May be used as measured state. |
| `MISSING` | No source value. | Preserve missing; no engineering-state imputation. |
| `IMPLAUSIBLE` | Present outside the documented quality window. | Preserve raw value in audit data; exclude from state-derived calculations. |
| `SEMANTICS_BLOCKED` | Source value exists, but field meaning/direction is not approved. | Preserve for traceability only. |
| `NOT_APPLICABLE` | Field is known not to apply to the stock/profile when a reliable applicability rule exists. | Preserve explicitly; do not treat as zero. |

## 4. Quality windows (not maintenance limits)

| Component | Valid source window | Basis |
| --- | ---: | --- |
| Diameter | 1000–1100 | Existing label quarantine and owner-provided new/condemning references. |
| Flange thickness | 10–50 | Existing degradation-semantics plausibility gate. |
| Root | 0–30 | Existing degradation-semantics plausibility gate. |
| Tire thickness | 5–100 | Existing degradation-semantics plausibility gate. |
| Wheel gauge | 1300–1700 | Existing degradation-semantics plausibility gate. |

These ranges only remove obvious source artefacts. They must not be used to trigger inspection, calculate a margin, or imply serviceability.

## 5. Margin layer — intentionally pending

An engineering margin is permitted only after all of the following are supplied for the relevant rolling-stock/profile class:

- authoritative dimension name and unit;
- intervention/condemning limit and inequality direction;
- applicability conditions and measurement method;
- whether the limit applies to a wheel, wheelset, axle, or vehicle;
- versioned source and effective date.

Until then, the following columns are prohibited: `diameter_margin`, `flange_margin`, `root_margin`, `tread_margin`, `qr_margin`, `minimum_margin`, and `limiting_dimension`.

The previous `phys_remaining_material_mm_*` fields remain experimental diameter references, not approved margins, because stock/profile applicability and limit governance are not yet encoded.

## 6. Derived fields permitted now

- Side-wise raw measurements and quality codes.
- Validity counts (for example, `n_valid_primary_measurements`).
- Same-timestamp side differences where both values are valid, labelled as **measurement consistency diagnostics**, not failure margins.
- Replacement/turning boundary flags based on recorded source events, labelled as observed maintenance context.
- Point-in-time-safe operational exposure and maintenance context with their source caveats retained.

## 7. Derived fields prohibited now

- A scalar health score or health class.
- Any rule-based “needs turning” label.
- Wear rates or cumulative material budgets across turning/replacement boundaries.
- QR, hollow-tread, flange-height, or profile margins from unresolved fields.
- Treating diameter and tire thickness as independent additive wear evidence.

## 8. Data-quality result

Across 1,165,641 source measurements, valid coverage after documented quality filtering is 98.9% for diameter, 89.7% for flange thickness, approximately 100% for root, 91.6% for tire thickness, and about 97% for wheel gauge. The blocked fields are generally populated but remain unavailable for engineering interpretation; availability is not semantic validity.

## 9. Required input to activate margins

The first external dependency is an approved limit register by rolling-stock/profile type. At minimum it must resolve:

1. applicability of the existing 1096 mm new / 1016 mm condemning diameter constants;
2. flange-thickness limit and measurement convention;
3. root limit and direction;
4. tire-thickness convention and whether it is redundant with diameter;
5. meanings and limits, if any, for `wsmFlange*`, `wsmThread*`, `wsmKvalue1`, and `wsmSDistance1`.

Until that register exists, this specification enables a defensible **measurement-state dataset**, but not margin-based engineering-need or inspection recommendations.

## 10. Changelog

| Version | Date | Change |
| --- | --- | --- |
| v1.0 | 2026-08-06 | Approved and frozen as versioned engineering contract. Added immutability & versioning section (v0); margin, health, and survival outputs remain blocked/forbidden as documented. |
