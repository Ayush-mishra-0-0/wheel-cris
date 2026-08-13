# V1.1 residual analysis — regression

- test rows: 28066

- **v1.0** MAE=16.539 · RMSE=23.103 · p95=45.119 · max=941.053
- **v1.1** MAE=11.681 · RMSE=15.702 · p95=30.387 · max=659.955

## Strata: MAE v1.0 -> v1.1 (top 20 improvements)

| stratum | value | n | MAE v1.0 | MAE v1.1 | change % | worst100 share 1.0->1.1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| home shed | PADX | 457 | 25.6 | 11.6 | -55% | 0.36->0.00 |
| home shed | ETE | 263 | 28.9 | 14.9 | -48% | 0.12->0.07 |
| home shed | GMOE  | 623 | 20.5 | 10.8 | -47% | 0.08->0.02 |
| home shed | CNBE | 271 | 17.2 | 9.4 | -46% | 0.04->0.00 |
| home shed | KYNE  | 835 | 20.5 | 11.7 | -43% | 0.16->0.04 |
| home shed | SPJD  | 278 | 19.5 | 11.3 | -42% | 0.00->0.00 |
| home shed | SGUD | 426 | 18.7 | 11.6 | -38% | 0.02->0.02 |
| home shed | BGKD | 584 | 19.2 | 12.0 | -38% | 0.00->0.02 |
| home shed | AQE   | 1697 | 17.4 | 11.2 | -36% | 0.06->0.04 |
| home shed | GZBE  | 1379 | 16.6 | 10.9 | -34% | 0.02->0.07 |
| home shed | SRCE | 579 | 15.3 | 10.1 | -34% | 0.02->0.02 |
| RTIS reporting coverage % | coverage Q4 | 5613 | 19.0 | 12.9 | -32% | 0.29->0.25 |
| interval wear, side 2 (mm) | wear2 Q3 | 5613 | 17.3 | 11.8 | -32% | 0.12->0.21 |
| interval wear, side 2 (mm) | wear2 Q4 | 5613 | 16.8 | 11.5 | -32% | 0.25->0.18 |
| interval wear, side 1 (mm) | wear1 Q4 | 5613 | 16.8 | 11.5 | -31% | 0.25->0.18 |
| interval wear, side 1 (mm) | wear1 Q3 | 5613 | 17.3 | 11.9 | -31% | 0.11->0.23 |
| interval wear, side 2 (mm) | wear2 Q5 | 5613 | 15.4 | 10.7 | -31% | 0.10->0.12 |
| home shed | EDE | 1008 | 16.6 | 11.5 | -31% | 0.00->0.04 |
| interval length (days) | interval Q3 | 5613 | 16.7 | 11.6 | -30% | 0.06->0.23 |
| turning event this interval | 1 | 307 | 18.4 | 12.8 | -30% | 0.00->0.01 |