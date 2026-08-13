# Railway Wheel Engineering Intelligence Platform

## Architectural position

The current product is an **Engineering Intelligence Platform**. It is not
called a Digital Twin because it does not yet have continuous telemetry,
physics simulation, state estimation, or closed-loop learning. Its purpose is
to provide a versioned, auditable engineering state foundation that can evolve
into a Digital Twin without reworking lower layers.

> Engineering Layer = what the platform knows from validated evidence.  
> Digital Twin Layer = what a future system continuously infers, simulates and
> learns from that evidence.

## Platform flow

```text
Bronze (immutable source snapshots)
  -> Silver (standardised, quality-flagged source records)
  -> Business Truth v1.0 (point-in-time equipment/wheelset assignment)
  -> Inspection Intervals v1.0 (validated temporal boundaries)
  -> Engineering Layer
       -> Identity | State | Exposure | Behaviour | Degradation
       -> Maintenance | Health | Prediction | Decision
  -> Feature Store (only validated Engineering Layer outputs)
  -> ML Models (later)
  -> Future Digital Twin Platform (streaming, physics, learning, simulation)
```

## Engineering Layer contract

| Layer | Responsibility | Current materialised truth | Never contains |
| --- | --- | --- | --- |
| Identity | Persistent asset and point-in-time assignment identity | Gold-B equipment/wheelset-candidate ID, assignment-history ID, locomotive ID/type, interval boundaries | Derived wear, health scores, predictions |
| State | Measured condition at a time | Wheel-measurement geometry and Silver quality flags at interval endpoints | Forecasts, recommendations, inferred sensor values |
| Exposure | What a validated asset experienced between endpoints | Interval duration; RTIS report/event context only | Unapproved km, health scores, causal claims |
| Behaviour | Time ordering and raw changes | Consecutive inspection intervals, raw geometry deltas, endpoint/loco transition status | Maintenance recommendation, RUL |
| Degradation | Engineering-approved physical change calculations | **Not materialised:** geometry deltas are raw evidence only | ML output, unvalidated wear calculations |
| Maintenance | Work/inspection/replacement evidence | Job-card presence/count by interval using creation time; raw turning indicators | Physics/wear calculation, maintenance-effectiveness claim |
| Health | Explainable condition indicators | **Not materialised:** requires approved limits and degradation rules | Raw source/sensor values, predictions |
| Prediction | Forecasts and uncertainty | **Not materialised** | Business rules, raw Bronze/Silver inputs |
| Decision | Action prioritisation and explanations | **Not materialised** | Training features, direct raw data |

`wsmEquipmentId` remains an equipment/wheelset-candidate identifier until
business semantics prove individual-wheel identity.

## Data-source mapping

| Layer | Current verified sources | Future sources / enrichments |
| --- | --- | --- |
| Identity | `WheelSetMeasurements`, `EquipmentMasterRegister`, `LocoEquipmentsHistory`, `LocoMaster`, `LocoTypes` | RFID, IoT asset registry, authoritative wheel lifecycle registry |
| State | `WheelSetMeasurements` | Online wheel profile scanners, condition sensors |
| Exposure | Inspection interval duration; RTIS report date/division context; RTIS emergency events | Approved RTIS distance rule, WAP7 FOIS movement feed, weather, track geometry, load |
| Behaviour | Gold-B inspection intervals, raw endpoint deltas | Streaming telemetry and validated operational sequences |
| Degradation | Approved future calculations from State + Exposure | Contact mechanics, material models, physics simulation |
| Maintenance | `SectionJobCards`, turning indicators, defect history | CMMS completion/work-order semantics, replacement records |
| Health | Derived later from approved State/Degradation/Maintenance rules | Physics-informed state estimation |
| Prediction | None | Regression, survival/RUL, calibrated uncertainty models |
| Decision | None | Maintenance capacity/optimisation engine, reviewed model outputs |

## Extensibility principles

1. New sources enrich an existing layer; they do not create ad-hoc layers.
2. Every derived metric has one owning Engineering Layer and reproducible lower
   layer lineage.
3. Raw measurements never enter Health, Prediction or Decision directly.
4. ML consumes versioned Engineering/Feature Store outputs, never Bronze,
   Silver, or unvalidated Gold-C data.
5. Every layer has its own contract version, quality criteria and release gate.
6. Missing/blocked enrichment is represented as coverage/status metadata—not
   imputed physical truth.
7. Gold-C/audit records remain available for data improvement but do not leak
   into high-confidence features or models.

## Current output boundaries

| Output | Owning layer | Status |
| --- | --- | --- |
| `business_truth/v1.0/wheel_timeline_gold_b` | Identity + State | Released |
| `inspection_intervals/v1.0/inspection_intervals_gold_b` | Behaviour | Released |
| Raw geometry delta columns | State/Behaviour evidence | Released; not degradation |
| RTIS distance | Exposure | Blocked by `rtis_distance_semantics.md` |
| Job-card interval presence/count | Maintenance | Released with creation-time limitation |
| Feature Store v1.0 | Feature Store | Released; automatic admission from feature specification only |
| Wear rate, health, prediction, decision products | Degradation onward | Not released |

## Product portfolio and feature governance

**Gold** is the technical persistence tier. It is not the name of every
consumer-facing output. Products are named by the engineering question they
answer:

```text
Engineering data products
  - Business Truth
  - Inspection Intervals
  - Operational Exposure
  - Engineering Features (next)
  - Feature Store (next)
  - Wheel Health Snapshot (next)
  - Fleet Health (next)
  - Decision Products (later)
```

The machine-readable source of truth for every feature is
[`configs/engineering_feature_specification_v1.json`](../../configs/engineering_feature_specification_v1.json).
It defines formula, unit, owner, time availability, lineage, validation rules,
status and consumer limits. Its companion JSON Schema and dependency-free
validator make the contract testable before a feature is materialised.

## Future Digital Twin extension

When continuous telemetry, physics models and outcome feedback become
available, add a **Digital Twin Platform above the Engineering Layer**:

```text
Streaming Sync + Physics/Simulation Engine + Learning Engine
                       -> Twin APIs / state estimation
                       -> versioned Engineering Layer state
```

Examples: vibration can feed a physics engine that estimates contact stress;
that estimated, versioned quantity then enriches Exposure/Degradation. The
Digital Twin does not bypass Business Truth or write untraceable values into
Health/Decision.
