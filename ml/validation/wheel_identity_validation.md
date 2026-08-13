# Wheel Identity Validation

**Status:** In progress — do not construct a wheel-level timeline yet.

## Question

For every wheel/equipment measurement, can we identify the locomotive that was
assigned **at that measurement time**?

## Required evidence

- Measurement equipment-ID completeness and match rate to the equipment master.
- Equipment-to-locomotive assignment coverage.
- Assignments per equipment and distinct locomotives per equipment.
- Provision-date completeness, ordering and repeated/transfer assignments.
- A confirmed removal/end-date source, or an engineering-approved rule for
  deriving an interval end from the next assignment.
- Point-in-time measurement-to-assignment match rate after interval logic is
  implemented.

## Current limitation

`LocoEquipments` exposes `LoeProvisionDate` but no confirmed removal date in
the discovered schema. We must not treat a static equipment-to-locomotive join
as historically correct. The next-provision date may become an interval end
only after duplicate/update behaviour is understood and approved.

## Initial static/cardinality evidence (2026-07-27)

- 1,168,636 source measurement rows; 1,144,280 have an equipment ID.
- All 109,813 distinct measurement equipment IDs exist in the equipment master.
- 85,904 of those IDs (78.23%) have a `LocoEquipments` row.
- `LocoEquipments` currently contains 2,145,916 rows and the same number of
  distinct equipment IDs: it behaves as one assignment row per equipment, not
  a transfer/history table.
- 199,659 assignment rows (9.30%) lack a valid provision date.
- There are no observed multi-assignment or multi-locomotive histories in this
  table, so it cannot prove an equipment item's past transfers or removal.

**Implication:** the next point-in-time coverage report can establish whether a
measurement is on/after the recorded provision date, but it cannot establish a
valid end date. Historical wheel-to-locomotive reconstruction remains blocked
until a transfer/removal history source or engineering-approved rule is found.

## Temporal-history evidence (2026-07-27)

`LocoEquipmentsHistory` closes much of the historical-assignment gap:

- 3,090,081 history rows; 2,616,174 equipment IDs.
- 106,998 of 109,813 measurement equipment IDs (97.44%) have history.
- 2,748,754 history rows have a valid provision date; 841,951 have a valid
  removed date; 28,021 have an invalid removed-before-provision order.
- Under the explicit interval rule `[provision_date, removed_date]`, with a
  missing removal treated as open-ended, 891,978 of 1,144,304 evaluated
  measurements (77.95%) match exactly one interval.
- 12,633 (1.10%) match multiple intervals and 239,693 (20.95%) match none.

**Eligibility rule for the first Wheel Timeline:** use only a measurement with
exactly one valid history interval. Ambiguous and unmatched records must remain
available with an exclusion reason; they are not eligible for exposure, wear or
RUL features until resolved.

## First WAP7 Gold-B timeline build

Within the WAP7 history candidate universe, 271,350 of 319,707 measurements
(84.87%) have exactly one valid interval. Gold-C exclusions contain 45,211
no-valid-interval records and 3,146 ambiguous-interval records. This is the
validated subset permitted to move to inspection-interval construction.

## Evidence queries

- `sql/validation/wheel_identity_validation.sql`
- `sql/validation/wheel_assignment_temporal_profile.sql`
- `sql/validation/measurement_assignment_point_in_time_coverage.sql`
- `sql/validation/loco_equipment_history_coverage.sql`
- `sql/validation/measurement_history_interval_coverage.sql`
