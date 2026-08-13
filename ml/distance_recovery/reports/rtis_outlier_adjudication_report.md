# RTIS outlier adjudication via FOIS reconstruction

Run: REAL run
Outlier loco-days: 3,880
Outliers with a FOIS witness that day: 98

| status | count | meaning |
| --- | ---: | --- |
| CONFIRMED_DOUBLE | 80 | RTIS double-counted -> replaced by FOIS recon |
| CONFIRMED_UNDER | 0 | RTIS undercounted -> replaced by FOIS recon |
| CONFIRMED_REAL | 0 | RTIS corroborated by FOIS -> RTIS kept |
| PARTIAL | 18 | in-between -> manual review |
| UNRESOLVED | 3,782 | no FOIS witness that day -> excluded, never zeroed |

Of the resolved outliers, 80 had their RTIS value corrected to the FOIS reconstruction.

## Examples

| loco | day | rtis_km | recon_km (FOIS) | ratio | status | final km |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 30206 | 2025-11-18 | 1,478.3 | — | nan | UNRESOLVED | nan |
| 30209 | 2023-12-07 | 1,485.5 | — | nan | UNRESOLVED | nan |
| 30209 | 2025-11-17 | 1,565.5 | — | nan | UNRESOLVED | nan |
| 30209 | 2025-11-22 | 1,513.1 | — | nan | UNRESOLVED | nan |
| 30211 | 2025-10-18 | 1,529.8 | — | nan | UNRESOLVED | nan |
| 30212 | 2024-09-08 | 1,477.0 | — | nan | UNRESOLVED | nan |
| 30212 | 2024-10-10 | 1,461.0 | — | nan | UNRESOLVED | nan |
| 30212 | 2025-07-08 | 1,543.0 | — | nan | UNRESOLVED | nan |
| 30214 | 2025-05-14 | 1,443.6 | — | nan | UNRESOLVED | nan |
| 30214 | 2025-10-20 | 1,350.8 | — | nan | UNRESOLVED | nan |
