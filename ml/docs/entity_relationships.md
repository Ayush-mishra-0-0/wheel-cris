# Canonical Entity Relationship Map

This document is the authoritative join map for the wheel RUL project. Use
surrogate keys for joins; use human-readable identifiers only for display and
cross-system reconciliation.

## Locomotive-type lookup (verified)

`LocoMaster.LomType` is an integer foreign key to `LocoTypes.LotId`.

| LocoTypes column | Meaning |
| --- | --- |
| `LotId` | Locomotive type code referenced by `LocoMaster.LomType` |
| `LotTypeName` | Human-readable locomotive type |

The 2026-07-24 lookup confirms `WAP7` maps to `LotId = 9`. Do not hard-code
that code in domain queries: resolve the configured cohort name through the
lookup table.

## Identity graph

```text
Wheel
  |
  | EquipmentMasterRegister.EmrId
  v
LocoEquipments.LoeEquipmentMasterRegister
  |
  | LocoEquipments.LoeLocoMaster
  v
LocoMaster.LomId ---- LocoMaster.LomNumber
  |
  +-- LocoMaster.LomType --> LocoTypes.LotId --> LocoTypes.LotTypeName
  |
  +-- RTIS
  +-- FOIS
  +-- Emergency
  +-- OnlineDefects
```

The wheel/equipment path and downstream system links above are the working
integration hypothesis supplied during discovery. Validate each foreign-key
column and each external system's locomotive identifier before implementing
its domain extraction.

## Cohort-first extraction contract

1. Set `experiment.cohort` in `configs/experiment.yaml`.
2. Run `python extract/build_cohort.py` to write
   `data/bronze/cohort_locomotives.parquet`.
3. Every domain query joins to the cohort using the stable `LomId` key.
4. Apply the configured time window within the relevant domain query.

This prevents repeated type-code filters and makes the same pipeline reusable
for a different locomotive family.
