# Data Dictionary: cohort_locomotives

| Column | Type | Null count | Null % | Distinct | Candidate key | Sample values | Min | Max | Mean | Comments |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- |
| LomId | int64 | 0 | 0.0000 | 21,727 | True | ["1", "2", "3", "4", "5"] | 1 | 24600 | 12622.863856 |  |
| LomNumber | str | 0 | 0.0000 | 21,727 | True | ["21107", "23055", "23067", "23068", "23092"] |  |  |  |  |
| LomType | int64 | 0 | 0.0000 | 55 | False | ["2", "1", "6", "18", "4"] | 1 | 61 | 20.599945 |  |
| LocoType | str | 0 | 0.0000 | 55 | False | ["WAG5T", "WAG5", "WAM4", "WAG5P", "WAG7"] |  |  |  |  |
| LomMake | int64 | 0 | 0.0000 | 9 | False | ["1", "6", "2", "9", "11"] | 1 | 14 | 4.254338 |  |
| LomCommissionDate | datetime64[us] | 339 | 1.5603 | 9,086 | False | ["1981-09-22T00:00:00", "1985-05-01T00:00:00", "1985-02-08T00:00:00", "1985-08-02T00:00:00", "1985-12-15T00:00:00"] | 1973-04-13T00:00:00 | 2026-07-24T00:00:00 |  |  |
| LomStatus | int64 | 0 | 0.0000 | 10 | False | ["2", "10", "4", "6", "5"] | 1 | 10 | 5.38749 |  |
