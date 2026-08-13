# Target Eligibility Matrix v1

**Decision basis:** a horizon benchmark is reportable only where its
`Eligible` cohort is large enough and its `Unknown follow-up` share is small
enough to be disclosed. Eligibility follows the tightened cohort definition
(event within horizon **or** full demonstrated follow-up), so every `Eligible`
row has a knowable horizon label.

| Horizon | Eligible rows | Eligible % | Events | Event rate | Censored (non-event) | Unknown follow-up | Unknown % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 d | 990,297 | 86.8% | 24,314 | 2.455% | 965,983 | 150,985 | 13.2% |
| 90 d | 942,869 | 82.6% | 46,100 | 4.889% | 896,769 | 198,413 | 17.4% |
| 180 d | 836,518 | 73.3% | 81,301 | 9.719% | 755,217 | 304,764 | 26.7% |
| 365 d | 633,225 | 55.5% | 117,719 | 18.590% | 515,506 | 508,057 | 44.5% |

## Reading the matrix

- **Eligible** = rows with a knowable outcome: event realised within the
  horizon, or at least `horizon` days of observed follow-up with no event.
- **Events** = recorded turnings realised within the horizon (equipment-day
  deduplicated).
- **Censored (non-event)** = full observed window with no realised event; the
  label is a demonstrated non-event, not an absence of record.
- **Unknown follow-up** = observation window shorter than the horizon and no
  event recorded; the horizon label is genuinely unknowable and these rows are
  excluded from the eligible cohort for that horizon.

## Reportability

Use this matrix to decide which horizons are scientifically reportable, and to
disclose the excluded (unknown) share per horizon before any binary benchmark
is trained.
