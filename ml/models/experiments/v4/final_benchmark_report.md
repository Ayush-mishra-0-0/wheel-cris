# Phase 4 — Production Risk-Ranking Benchmark (Final Report)

- **Date:** 2026-08-19
- **Status:** COMPLETE — rolling production simulation + never-seen-loco stress + attribution + Wheel Risk Card
- **Governing plan:** `docs/phase4_plan.md` (v1.1)
- **Label/eligibility contract:** `docs/contracts/risk_event_contract_v1.md` (v1.1, immutable)
- **Wear limits:** `configs/limit_register_v1.json` (Wrpld table, ratified 2026-08-19) — root condemning limit is **6 mm**; earlier runs used the superseded 3 mm figure and are **historical only**.
- **Question answered:** *Can we produce a trustworthy top-N inspection list for root>6mm and turning within 30/90/180 days?*

  **Turning: yes** — stable, well-calibrated, transfers to never-seen locomotives.
  **Root>6 mm: no (not statistically operable).** At the true Wrpld limit the event is too rare (~0.03–0.2 % prevalence) for any model to rank with confidence; this is a data-prevalence limitation, not a modelling failure.

---

## 1. Setup

| Item | Value |
|---|---|
| Cohort | Within-lifecycle wheel inspections (v4 anchor; row/split identity frozen from v3f) |
| Rows | 239,684 |
| Targets | A = root>6mm constraint (Wrpld condemning, `configs/limit_register_v1.json`), B = turning realization (`turning_record_at_measurement==1`) |
| Horizons | 30 / 90 / 180 days, event strictly inside `(t, t+H]` |
| Leakage control | Point-in-time: per-equipment observation capped at cutoff `T`; label only counts events occurred ≤ `T`; frozen v4 PIT features |
| Turning source | WES `wheel_engineering_state_v1.0.parquet` (v3f `turning_record_at_measurement` is all-zero) joined via `measurement_record_id` |
| Models | B0 prevalence/random · B1 regularized logistic · B2 margin-only logistic (6−root) · C1 XGBoost (candidate) |
| Eval protocol | Monthly refit at 30-day cutoffs; metrics reported as **median across cutoffs** (never best-cutoff) |
| Metrics | PR-AUC (primary), ROC-AUC, Brier, ECE, capture@5%/10%, lift@5%/10% |
| Dataset manifest | `model_datasets/v4/risk_benchmark_manifest.json`, sha256 `8b0595c03465d89f230c09b0de101bd44c53c2e1c0945582bdaa3815e3acdc5d` |

## 2. Rolling production simulation (PRIMARY — plan §7)

Candidate C1 vs baselines. Median PR-AUC and capture@10% across cutoffs (n = cutoffs):

### Root constraint (>6 mm)
| Horizon | B0 (prev) | B1 logistic | B2 margin | C1 XGB | C1 ROC-AUC | C1 cap10% | n cutoffs |
|---|---|---|---|---|---|---|---|
| 30d | — | — | — | — | — | — | **0** (no evaluable cutoffs) |
| 90d | 0.002 | 0.006 | 0.002 | **0.109** | 0.570 | **0.195** | 6 |
| 180d | 0.003 | 0.004 | 0.004 | **0.011** | 0.590 | **0.233** | 11 |

### Turning realization
| Horizon | B0 (prev) | B1 logistic | B2 margin | C1 XGB | C1 ROC-AUC | C1 cap10% | n cutoffs |
|---|---|---|---|---|---|---|---|
| 30d | 0.009 | 0.135 | 0.035 | **0.340** | 0.948 | **0.787** | 41 |
| 90d | 0.021 | 0.183 | 0.062 | **0.340** | 0.925 | **0.781** | 53 |
| 180d | 0.041 | 0.150 | 0.090 | **0.397** | 0.927 | **0.714** | 57 |

**Headline (30d/90d, the operative horizons):**
- **Turn-90d:** C1 captures **78%** of realized turnings in the top 10% of the ranked list and **58%** in the top 5% (lift@5% ≈ 11.5×). This reproduces the Phase 3A "Recall@Top-5% ≈ 48 %" result and improves on it.
- **Turn-30d / 180d:** robust — capture@10% 0.79 / 0.71 (ROC 0.948 / 0.927). Turning is the operationally strong target.
- **Root-30d:** **not reportable** — with the corrected 6 mm limit, root events in 30 days are so rare (≈0.03 % of eligible rows) that no cutoff produced stable metrics (n cutoffs = 0).
- **Root-90d/180d:** C1 edges above baselines on PR-AUC but ROC-AUC ≈ 0.57–0.59 is weak, and it is driven by a handful of events (6 / 11 evaluable cutoffs). Treat any root>6 mm ranking as **exploratory only**.

**Calibration:** turning Brier/ECE are small at 30d (0.007/0.004) and 90d (0.021/0.017); 180d is degraded (ECE 0.070) — rank-only at 180d. Root Brier is tiny (0.002/0.004) but this reflects near-total dominance of the negative class, not predictive value.

## 3. Never-seen-loco stress (SECONDARY — plan §8)

422 of 2,110 locomotives fully withheld (all rows, all time); fit only on seen locos; score held-out locos. This is a **transferability stress**, not a benchmark.

| Target | Horizon | n eval | eval events | C1 cap10% | C1 ROC-AUC | B0 cap10% |
|---|---|---|---|---|---|---|
| root | 30d | 45,926 | 16 | **0.313** | 0.660 | 0.250 |
| root | 90d | 43,106 | 55 | **0.200** | 0.580 | 0.109 |
| root | 180d | 37,050 | 103 | **0.291** | 0.659 | 0.039 |
| turn | 30d | 45,947 | 237 | **0.751** | 0.914 | 0.000 |
| turn | 90d | 43,205 | 744 | **0.864** | 0.950 | 0.000 |
| turn | 180d | 37,423 | 1,573 | **0.796** | 0.941 | 0.000 |

**Verdict:**
- **Turning generalizes strongly** to never-seen locomotives (capture@10% 0.75–0.86, ROC 0.91–0.95) — the model learns general wheel behaviour, not per-loco memory.
- **Root does not transfer** (30d held out only 16 root events; ROC 0.58–0.66 ≈ noise). This confirms the primary finding: root>6 mm is too sparse for production ranking, not that the model "does not learn" — there is almost nothing to learn from.

## 4. Attribution and Wheel Risk Card (plan §9)

- `models/phase4/run_attribution.py` fits C1 point-in-time at the latest cutoff (2026-06-30) and produces SHAP attribution for the 4,098-wheel trailing batch per target.
- Top contributors are physically sensible: root **margin** dominates root-constraint risk; **days-since-last-turning**, **home shed**, wheel position/profile and exposure (km) drive turning risk.
- `models/phase4/render_risk_card.py` renders the per-wheel artifact; sample:

```
WHEEL ENGINEERING RISK CARD
Wheelset 746177 / Loco 9612 / 2026-06-23
90-DAY MAINTENANCE RISK          ████████████  HIGH
ROOT CONSTRAINT RISK             ████████████  HIGH
LIMITING DIMENSION               ROOT (margin +3.62 mm)
CURRENT STATE                    Dia 1056.6 / Root 2.38 / Flange 31.50 / Gauge 1595.50 (mm)
LIKELY CONTRIBUTORS              1 Exposure (km)  2 Inspection history  3 Wheel gauge  4 Home shed
                                  1 Home shed  2 Days since last turning  3 Root margin  4 Inspection history
ACTION                           → PRIORITY INSPECTION
MODEL CONFIDENCE                 calibrated band: ~19% 90d event rate (decile 9/10, train)
```

Note: `LIMIT_ROOT = 6.0` (Wrpld); the card shows margin `+3.62 mm` for a Root reading of 2.38 mm.

## 5. Conclusions and guardrails

1. **Production-ready for the top-N turning list at 30/90d** (capture@10% 0.78–0.79, ROC ≈ 0.93–0.95, transfers to never-seen locos). This is the shipping use-case.
2. **Root>6 mm is NOT production-ready** — prevalence ≈0.03–0.2 % makes ranking statistically uninformative (30d has no evaluable cutoffs). Options: (a) use a pre-condemning early-warning threshold for root (e.g. margin-based watch bands) as a *soft* flag, not a ranking target; (b) gather more data / longer horizon; (c) keep root out of the production list and rely on turning + diameter margin.
3. The earlier root target (3 mm) was based on a **superseded** figure (Q8 / §3.3); all v4 artifacts were rebuilt with `limit_root_mm: 6.0` on 2026-08-19. Prior 3 mm numbers in older reports are historical.
4. Attribution is **model attribution, never "cause"** (contract §8 semantics).
5. Reported medians, never best-cutoff.
6. Out-of-scope (per plan): diameter regression (closed Phase 3F), Cox/RSF survival, deep learning, tuning.

## 6. Artifacts

| File | Description |
|---|---|
| `configs/limit_register_v1.json` | Approved Wrpld wear register (flange 3.0 / root 6.0 / tread 6.5) |
| `model_datasets/v4/risk_benchmark.parquet` | Frozen PIT feature/label benchmark set (239,684 rows, limit_root_mm 6.0) |
| `model_datasets/v4/risk_benchmark_manifest.json` | Dataset manifest + SHA256 |
| `models/phase4/build_risk_benchmark.py` | Dataset build |
| `models/phase4/run_rolling_risk_benchmark.py` | Rolling production simulation (PRIMARY) |
| `models/experiments/v4/rolling_risk_benchmark.json` | Primary results (per-cutoff + median/IQR) |
| `models/phase4/run_loco_holdout.py` | Never-seen-loco stress |
| `models/experiments/v4/loco_holdout.json` | Stress results |
| `models/phase4/run_attribution.py` | Per-wheel SHAP attribution |
| `models/experiments/v4/wheel_attribution_{root,turn}.parquet` | Attribution (4,098 rows each) |
| `models/phase4/render_risk_card.py` | Wheel Risk Card renderer |
| `models/experiments/v4/risk_cards/` | Rendered cards |
