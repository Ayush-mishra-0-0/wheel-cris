# Phase 3 Target & Evaluation Contract v2.0

**Status:** Draft for engineering-owner review  
**Project objective:** Estimate wheel engineering state and prioritize maintenance actions under observational constraints.  
**Primary evaluation:** Rolling temporal evaluation.  
**Scope:** This contract supersedes the baseline model framing for Phase 3 only. It does not alter or overwrite v1.x/v2 datasets, labels, or results.

## 1. Scientific model and claim boundary

```text
Observed inspection measurements + point-in-time-safe operating context
    -> Wheel Engineering State (observed / derived)
    -> Latent Engineering Need (unobserved)
    -> Maintenance Realization (observed)
```

`wsmturning1` is an observed maintenance-realization record. It is not a direct label of latent engineering need and must never be described as such. A model trained on it estimates the probability or timing of recorded maintenance realization under the available operating and policy environment.

The benchmark estimates maintenance realization under partial observability and does not claim to recover the latent engineering decision process.

## 2. Concepts and permitted claims

| Concept | Observability | Definition | Permitted use |
| --- | --- | --- | --- |
| Wheel Engineering State | Observed / derived | Versioned vector of measured dimensions, approved margins, quality flags, and operating context at an inspection boundary. | Input and engineering-intelligence output. |
| Latent Engineering Need | Unobserved | Whether the wheel has reached, or will reach, an engineering intervention condition. | Research construct only; no supervised truth claim. |
| Maintenance Realization | Observed, imperfect | A deduplicated recorded `wsmturning1` event. | Classification, survival, and ranking outcome. |
| Engineering RUL | Latent | Time/distance to an engineering-limit crossing. | Not estimated as validated ground truth in v2.0. |
| Maintenance RUL | Observed, censored | Time/distance to recorded maintenance realization. | Survival outcome, labelled as maintenance RUL. |
| Inspection RUL | Decision output | Recommended time/distance until review, based on risk, ranking, and policy capacity. | Deployment decision aid; not an observed target. |

## 3. Causal assumptions and data limitations

| Category | Variables / processes |
| --- | --- |
| Observed | Inspection measurements, point-in-time-safe RTIS/FOIS exposure, maintenance history, recorded turning flag. |
| Partially observed | Maintenance opportunity, locomotive-level jobcards, workshop batching, fleet-level actions. |
| Unobserved | True engineering trigger, operator judgement, minimum-cut optimization, workshop scheduling/capacity, complete reason/action records. |

Consequences:

- Calibration is for **maintenance realization**, not engineering-limit failure.
- A negative event can represent either no engineering need or unrealized/delayed need.
- Co-turned wheelsets and jobcard context are diagnostic/context variables, not causal proof.
- All reports must include this limitation and must not use “true RUL.”

## 4. Approved Phase 3 outcomes

### 4.1 Track A — Decision Intelligence

| Task | Outcome | Unit / horizon | Primary use |
| --- | --- | --- | --- |
| Risk classification | Recorded maintenance realization | 30, 90, 180, 365 calendar days after score boundary | Inspection prioritization. |
| Survival | Maintenance RUL | Days to deduplicated recorded realization; right-censored at verified observation end | Risk ordering over time. |
| Ranking | Same risk outcome | Top 1%, 5%, 10%, and capacity-defined top-k | Inspection queue selection. |

The horizon labels are provisional until the event/censoring audit verifies adequate follow-up and event counts at each horizon.

### 4.2 Track B — Engineering Intelligence

Output a Wheel Engineering State for each valid inspection boundary:

- raw measured dimensions and units;
- approved margin-to-limit fields once limits are signed off by stock/profile type;
- limiting observed margin/dimension where comparable margins exist;
- measurement-quality and missingness flags;
- point-in-time-safe operational and maintenance context.

Track B may identify a limiting **observed condition**. It must not label that condition as the causal reason for turning unless a wheelset-level maintenance reason/action source validates it.

## 5. Target definitions

### 5.1 Maintenance-realization event

The working event is a **deduplicated recorded turning realization** derived from `wsmturning1 == 1`. Deduplication rules, timestamp semantics, side agreement, repeated flags, and replacement/reprofiling handling are deferred to the Event & Censoring Audit. Until approved, the label remains `CANDIDATE`.

`next_interval_large_loss_flag` is excluded from Phase 3 primary outcomes because its threshold is below the measured repeatability floor and it conflates multiple processes.

### 5.2 Survival target

For each score boundary `t0`, time is calendar days from `t0` to the first approved maintenance-realization event strictly after `t0`. No such event is right-censored only at a verified per-wheelset observation end, not at a global nominal dataset end. Models must use all censored rows.

### 5.3 Exclusions

- No continuous-diameter-delta regression is a Phase 3 success target.
- No observed-only survival fit is permitted.
- No model may include identifiers, future measurements, post-event action fields, or post-score-boundary jobcard facts as predictors.

## 6. Evaluation protocol

### 6.1 Primary: rolling production simulation

At each frozen cutoff `T`:

1. Train only on examples whose outcome observation is complete by `T`.
2. Score only wheel inspection states known by `T`.
3. Evaluate their future realized outcomes without exposing any future measurements, events, or post-`T` context to the model.
4. Report every cutoff and a distribution across cutoffs; do not headline only the best cutoff.

Grouped wheelset holdout is secondary diagnostic evaluation. It must prevent any wheelset from spanning splits but does not replace rolling evaluation.

### 6.2 Required baselines

- Prevalence/constant-risk classifier.
- Regularized logistic regression with the approved state/context feature set.
- Cox proportional hazards baseline using censored data.
- Rule-based engineering-state ranking, once margins are approved.

Tree/boosting and random-survival-forest models are comparator models, not automatic champions.

## 7. Metrics and operational KPIs

| Task | Primary metric | Required supporting metrics |
| --- | --- | --- |
| Classification | PR-AUC | ROC-AUC, Brier, calibration curve/ECE, prevalence, confidence intervals. |
| Survival | Harrell C-index | Horizon calibration, integrated Brier score where feasible, Kaplan-Meier curves by predicted-risk group. |
| Ranking | Recall@top-k / event capture@top-k | Precision@top-k, lift over prevalence, workload, capture at top 1%, 5%, 10%, and stakeholder capacity. |

For a selected inspection capacity `k`, report:

```text
event capture@k = future realized maintenance events among top-k ranked states
                   / all future realized maintenance events in the evaluation window
```

Operational thresholds may be chosen only on historical training/validation windows, then frozen for the subsequent rolling evaluation window.

## 8. Mandatory reporting

Every Phase 3 result must record:

- Dataset, state-specification, target-specification, and split versions.
- Observation-end and censoring rules.
- Event prevalence, censoring percentage, and available follow-up at each horizon.
- Rolling-cutoff results, calibration, and ranking workload/capture.
- Stability by calendar period, shed, wheel/profile type, and measurement-quality/missingness strata.
- The causal-claims boundary in Section 1.

## 9. Acceptance gates

No predictive benchmark begins until these gates pass:

1. Maintenance-realization event deduplication and timestamp semantics are approved.
2. Observation-end/censoring rule is reproducible per wheelset.
3. At least one rolling cutoff has sufficient events for each reported horizon; otherwise that horizon is suppressed.
4. Engineering limits and units are approved before margin fields are called margins or used in rule-based ranking.
5. The target-quality report enumerates exclusions, missingness, and policy/batching limitations.

## 10. Immediate next step

Define the Wheel Engineering State specification: dimensions available today, source units, quality checks, pending limits, missingness semantics, and the procedure for adding approved engineering margins.
