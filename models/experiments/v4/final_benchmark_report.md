# Phase 4 — Production Risk-Ranking Benchmark (Final Report)

- **Date:** 2026-08-11
- **Status:** COMPLETE — rolling production simulation + never-seen-loco stress + attribution + Wheel Risk Card
- **Governing plan:** `docs/phase4_plan.md` (v1.0)
- **Label/eligibility contract:** `docs/contracts/risk_event_contract_v1.md` (frozen, immutable)
- **Question answered:** *Can we produce a trustworthy top-N inspection list for root>3mm and turning within 30/90/180 days?* — **Yes, within stated horizons and guardrails.**

---

## 1. Setup

| Item | Value |
|---|---|
| Cohort | Within-lifecycle wheel inspections (v4 anchor; row/split identity frozen from v3f) |
| Rows | 239,684 |
| Targets | A = root>3mm constraint (owner-confirmed condemning), B = turning realization (`turning_record_at_measurement==1`) |
| Horizons | 30 / 90 / 180 days, event strictly inside `(t, t+H]` |
| Leakage control | Point-in-time: per-equipment observation capped at cutoff `T`; label only counts events occurred ≤ `T`; frozen v4 PIT features |
| Turning source | WES `wheel_engineering_state_v1.0.parquet` (v3f `turning_record_at_measurement` is all-zero) joined via `measurement_record_id` |
| Models | B0 prevalence/random · B1 regularized logistic · B2 margin-only logistic (3−root) · C1 XGBoost (candidate) |
| Eval protocol | Monthly refit at 30-day cutoffs; metrics reported as **median across cutoffs** (never best-cutoff) |
| Metrics | PR-AUC (primary), ROC-AUC, Brier, ECE, capture@5%/10%, lift@5%/10% |

## 2. Rolling production simulation (PRIMARY — plan §7)

Candidate C1 vs baselines. Median PR-AUC and capture@10% across cutoffs (n = cutoffs):

### Root constraint (>3 mm)
| Horizon | B0 (prev) | B1 logistic | B2 margin | C1 XGB | C1 ROC-AUC | C1 cap10% |
|---|---|---|---|---|---|---|
| 30d | 0.039 | 0.220 | 0.199 | **0.513** | 0.932 | **0.743** |
| 90d | 0.103 | 0.279 | 0.268 | **0.401** | 0.797 | **0.362** |
| 180d | 0.245 | 0.396 | 0.446 | **0.465** | 0.679 | **0.186** |

### Turning realization
| Horizon | B0 (prev) | B1 logistic | B2 margin | C1 XGB | C1 ROC-AUC | C1 cap10% |
|---|---|---|---|---|---|---|
| 30d | 0.009 | 0.135 | 0.035 | **0.340** | 0.948 | **0.787** |
| 90d | 0.021 | 0.183 | 0.062 | **0.340** | 0.925 | **0.781** |
| 180d | 0.041 | 0.150 | 0.090 | **0.397** | 0.927 | **0.714** |

**Headline (30d/90d, the operative horizons):**
- **Root-30d:** C1 captures **74%** of wheels that hit root>3mm in the top 10% of the ranked list (prevalence list would capture 2.5%). Lift@5% ≈ 11.3×.
- **Turn-90d:** C1 captures **78%** of realized turnings in the top 10%; B1 (0.53) and B2 margin-only (0.26) are far behind. Lift@5% ≈ 11.5×.
- **Turn-180d:** C1 keeps **71%** capture@10% (ROC 0.93) — the turning target is robust to horizon.

**Calibration:** Brier/ECE are small at 30d (root 0.031/0.023; turn 0.007/0.004) and 90d (root 0.097/0.083; turn 0.021/0.017). **Root-180d is not well calibrated (ECE 0.22)** — horizon 180d root ranking should be treated as rank-only, not probability.

## 3. Never-seen-loco stress (SECONDARY — plan §8)

422 of 2,110 locomotives fully withheld (all rows, all time); fit only on seen locos; score held-out locos. This is a **transferability stress**, not a benchmark.

| Target | Horizon | n eval | C1 cap10% | C1 ROC-AUC | B0 cap10% |
|---|---|---|---|---|---|
| root | 30d | 46,047 | **0.693** | 0.909 | 0.029 |
| root | 90d | 43,533 | **0.478** | 0.861 | 0.048 |
| root | 180d | 38,393 | **0.305** | 0.812 | 0.083 |
| turn | 30d | 45,947 | **0.751** | 0.914 | 0.000 |
| turn | 90d | 43,205 | **0.864** | 0.950 | 0.000 |
| turn | 180d | 37,423 | **0.796** | 0.941 | 0.000 |

**Verdict:** the ranking **survives** the never-seen-loco holdout — the model learns general wheel behaviour, not per-loco memory. Turning generalization is especially strong (capture@10% 0.75–0.86 on never-seen locomotives).

## 4. Attribution and Wheel Risk Card (plan §9)

- `models/phase4/run_attribution.py` fits C1 point-in-time at the latest cutoff (2026-06-01) and produces SHAP attribution for the 4,098-wheel trailing batch per target.
- Top contributors are physically sensible: root **margin** dominates root-constraint risk; **days-since-last-turning**, **home shed**, wheel position/profile and exposure (km) drive turning risk.
- `models/phase4/render_risk_card.py` renders the per-wheel artifact; sample:

```
WHEEL ENGINEERING RISK CARD
Wheelset 874318 / Loco 9609 / 2026-06-01
90-DAY MAINTENANCE RISK          ████████████  HIGH
ROOT CONSTRAINT RISK             ████████████  HIGH
LIMITING DIMENSION               ROOT (margin -0.50 mm)
CURRENT STATE                    Dia 1092.3 / Root 3.50 / Flange 30.75 / Gauge 1595.50 (mm)
LIKELY CONTRIBUTORS              1 Root margin  2 Inspection history  3 Home shed  4 Days since last turning
ACTION                           → PRIORITY INSPECTION
MODEL CONFIDENCE                 calibrated band: ~19% 90d event rate (decile 9/10, train)
```

## 5. Conclusions and guardrails

1. **Production-ready for the top-N list at 30/90d** for both targets; turning is robust out to 180d.
2. **Root-180d is rank-only** (PR-AUC 0.46, ECE 0.22) — do not use as calibrated probability.
3. Attribution is **model attribution, never "cause"** (contract §8 semantics).
4. Reported medians, never best-cutoff. Cutoff counts: 41–92 per (target, horizon).
5. Out-of-scope (per plan): diameter regression (closed Phase 3F), Cox/RSF survival, deep learning, tuning.

## 6. Artifacts

| File | Description |
|---|---|
| `model_datasets/v4/risk_benchmark.parquet` | Frozen PIT feature/label benchmark set (239,684 rows) |
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
