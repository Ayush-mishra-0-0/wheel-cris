# Engineering feature readiness catalog

> Superseded as the governing artifact by
> [`configs/engineering_feature_specification_v1.json`](../configs/engineering_feature_specification_v1.json).
> This page is a human-readable summary only; the structured specification,
> schema and validator control feature release.

This is the release register for Version 1. A feature is usable only at the
grain and semantic status shown below.

| Feature | Layer | Status | Evidence / constraint |
| --- | --- | --- | --- |
| Inspection interval duration | Behaviour | READY | 225,262 positive-duration Gold-B intervals. |
| Measurement deltas | Behaviour | READY AS RAW DELTAS | They are factual endpoint differences; turning/replacement semantics still prevent a wear-rate claim. |
| RTIS source-event count and event-type values | Exposure | READY WITH EVENT-CODE CAVEAT | 783 WAP-cohort source records have transmission timestamps; code-to-engineering-event meaning remains pending. |
| Job-card creation count | Maintenance / Exposure | READY WITH SEMANTIC CAVEAT | 4.43M source job cards; creation time is not confirmed completion or effect. |
| RTIS reporting coverage and duplicate metadata | Exposure | READY AS PROVISIONAL METADATA | Does not represent movement, route or kilometres. |
| Static WAP7 axle-load configuration | Exposure | READY WITH UNIT VALIDATION | `LocoTypes` provides `LotAxelLoad=20.5`; validate engineering unit before presentation. |
| Interval RTIS distance / distance per day | Exposure | BLOCKED | RTIS distance semantics unresolved; physically implausible aggregations observed. |
| Wear rate (mm/day) | Degradation | PENDING | Requires turning/replacement and measurement-unit/range rules. |
| Wear rate (mm/km) | Degradation | BLOCKED | Requires released interval distance plus wear semantics. |
| Health/risk score | Health | BLOCKED | Requires approved geometry limits, intervention semantics and score validation. |
| FOIS route exposure | Exposure | BLOCKED FOR WAP7 | Identifier reconciliation succeeds, but current FOIS extract has no WAP-family coverage. |
| Track curve/gradient severity | Exposure | WAITING FOR DATA | No authoritative, mappable track-geometry source acquired. |
| Weather context | Exposure | PENDING | External historical-enrichment design and coordinate-quality validation required. |
| Dynamic load index | Exposure | PENDING | Train attachment exists; no validated time-varying load measure. |
| RUL/prediction | Prediction | BLOCKED | Needs released degradation labels, endpoint/censoring policy and time-safe feature set. |
