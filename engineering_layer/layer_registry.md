# Engineering Layer Registry

The normative architecture contract is
[`docs/architecture/engineering_intelligence_platform.md`](../docs/architecture/engineering_intelligence_platform.md).

| Layer | Intended output namespace | Current state |
| --- | --- | --- |
| Identity | `data/engineering/identity/` | Business Truth v1.0 is the current source |
| State | `data/engineering/state/` | **FROZEN v1.0** — Wheel Engineering State v1.0 immutable |
| Exposure | `data/engineering/exposure/` | Duration only; km blocked |
| Behaviour | `data/engineering/behaviour/` | Inspection Intervals v1.0 released |
| Degradation | `data/engineering/degradation/` | Blocked pending engineering rules |
| Maintenance | `data/engineering/maintenance/` | Event presence/count validated with limitations |
| Health | `data/engineering/health/` | Not released |
| Prediction | `data/engineering/prediction/` | Not released |
| Decision | `data/engineering/decision/` | Not released |

No layer may publish an artifact until it has a versioned contract, validation
evidence and an owning implementation.
