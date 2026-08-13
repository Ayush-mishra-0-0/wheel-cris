# FOIS track-history map-matching report

Track-history rows: 15,574,443 · locos: 2,271 · transitions: 8,475,769
Station reference match rate: 79.46%
Transitions on the SAME rail edge (rail_km computed): 34.8%

Daily aggregation rows (loco x day): 339,365

## Rail vs geodesic (transitions with both)

- transitions with rail_km AND geo_km: 2,947,941
- median rail/geo ratio: 1.03 (>1 expected: rail >= geodesic)
- share where rail_km >= geo_km: 88.9%

## Sample transitions

| loco | station_a | station_b | geo_km | rail_km | same_edge |
| --- | --- | --- | ---: | ---: | ---: |
| 30201 | LDHE | BHOI | nan | nan | False |
| 30201 | BHOI | LDH | 3.01 | nan | False |
| 30201 | LDH | JGN | 37.88 | nan | False |
| 30201 | JGN | MOGA | 29.12 | 29.31 | True |
| 30201 | MOGA | PHS | 37.51 | 37.94 | True |
| 30201 | PHS | FZR | 16.95 | 17.01 | True |
| 30201 | FZR | KBU | 10.8 | nan | False |
| 30201 | KBU | FDK | 21.16 | 21.17 | True |
| 30201 | FDK | KKP | 12.81 | nan | False |
| 30201 | KKP | GNA | 30.18 | 30.34 | True |
| 30201 | GNA | BTI | 12.34 | nan | False |
| 30201 | BTI | MASK | 23.35 | nan | False |
| 30201 | MASK | SSZ | 19.56 | 19.83 | True |
| 30201 | SSZ | BLZ | 24.69 | 24.7 | True |
| 30201 | BLZ | JHL | 29.67 | nan | False |
