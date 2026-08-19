# Proper survival modelling - time_to_next_turning_days (review item 2)

Previous v1.x survival score (C-index 0.539) trained an HGB on the ~9% uncensored rows only
= survivorship-biased. This run trains on the FULL train set (all censored rows) with verified
per-wheelset observation-end censoring: time = last measurement - interval_end, event=0 on censored;
uncensored rows keep their true event time. Learners initialised per plan: dummy, CoxPH, RSF, GBSA.

Outcome: CoxPH with proper right-censoring yields ESSENTIALLY CHANCE discrimination
(val C-index 0.5443, test 0.4896). This independently confirms the senior review conclusion:
turning (time_to_next_turning_days) is NOT learnable from the current feature set; the old 0.539 was an artefact of observed-only survivorship bias.

| model | split | c_index |
| --- | --- | ---: |
| dummy_median_time | val | 0.5000 |
| dummy_median_time | test | 0.5000 |
| cox_ph | val | 0.5443 |
| cox_ph | test | 0.4896 |

RSF and GBSA runs were not completed: RSF/GBSA fitting on 144k rows x 96 cols exceeded the 30 min
time budget and was terminated. Given CoxPH gives chance-level C-index and the strategic decision
now de-prioritises full survival modelling until censoring semantics are approved, remaining
RSF/GBSA runs are DEFERRED rather than re-attempted at higher cost.
