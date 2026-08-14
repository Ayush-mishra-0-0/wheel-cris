# Dashboard Roadmap — Wheel Lifecycle Intelligence (Layer 5)

> Working plan for turning the current single-loco dashboard into a production-oriented tool
> engineers can use day to day. Tick items off with `- [x]` as they land.
> Related: `ml/docs/ml_correctness_analysis.md` (ML findings), `future_work.md` (deferred enterprise hygiene).
>
> Last updated: 2026-08-14

## Important caveat — this becomes a module inside the SLAM ecosystem

This dashboard is likely to become a page/module inside the existing **SLAM application**.
Consequences:

- **Authentication, SSO, RBAC and user management are NOT built here.** The SLAM host application
  owns that boundary. Building our own identity stack now is duplicated work that will be thrown
  away on integration.
- **What transfers directly** (and what we invest in heavily): correct ML outputs, a clean typed
  FastAPI contract, the fleet engineering UI, and deployment reproducibility.
- We only assume the API may be wrapped by another client; we make **no assumptions about who
  authenticates callers** and we implement **no auth here**.

```text
             Wheel RUL / Profile Service
                       │
                 FastAPI API  (this project — contract of record)
                       │
          ┌────────────┴────────────┐
          │                         │
     Current UI                 Future SLAM UI
       (React)                    (SLAM host)
          │                         │
          └────────────┬────────────┘
                       │
                 Same API contract
```

## Guiding principles

1. **Correct ML/engineering outputs first.** The physically invalid increasing-diameter forecast
   must be understood and fixed before it is presented as an engineering output.
2. **Fleet usability is the goal.** The main operational question: *"What wheelsets should an
   engineer inspect/pay attention to today?"* — answered with degradation state, proximity to
   engineering limits **and** P(turn) as separate signals (P(turn) is shed-maintenance behaviour,
   NOT an engineering failure threshold, so it is never the sole ranking signal).
3. **One chart-data contract.** A single versioned backend contract feeds both the interactive
   React/ECharts charts and the Matplotlib SVG exports. Lifecycle/forecast transformation logic
   lives once, on the backend; the charting layer stays a thin, swappable renderer.
4. **API-first, integration-ready.** The FastAPI layer is the contract of record — reusable by the
   current React UI and by SLAM. Typed schemas, versioning, env-based config, no auth assumptions.
5. **No application-level auth/identity work now.** SLAM provides that boundary. Docker only as one
   simple Compose for reproducibility — not a deployment architecture phase.

---

## P0 — ML / engineering correctness (gate)

Nothing in P1–P4 may present a degradation forecast as an engineering output until P0 is closed.

### P0.1 — Analysis (done → `ml/docs/ml_correctness_analysis.md`)

- [x] Diagnose the "why is diameter increasing" question (analysis doc written).
- [x] Assess prediction quality from `ml/models/experiments/v5/degradation_benchmark.json` +
      `fleet_backtest.json` (analysis doc written).

### P0.2 — Fix diameter forecasting

- [x] Audit replacement/boundary detection for missed wheel replacements (a missed replacement puts a
      larger-diameter measurement inside the anchor's "same segment" target and teaches the model that
      diameter can rise).
  - [x] Scan all wheelset dia series for jumps > ~20 mm that are NOT flagged `turn_event`/`replacement`.
        → **4,127 of 7,928 (52%) ≥20 mm up-jumps missed** by the serving boundary heuristic.
  - [x] Quantify contamination share of `degradation_benchmark.parquet` targets.
        → **3.3–5.0% of dia targets rise** (median +2→+26 mm by horizon; p99 ≈ +70 mm).
  - [x] Add a standalone audit script under `ml/models/` + commit results (like the phase-3 audits).
        → `ml/models/replacement_contamination_audit.py` →
        `ml/models/experiments/v5/replacement_contamination_audit.json` (see `ml/docs/ml_correctness_analysis.md` §1.5).
- [x] Model **change/delta** (Δdim over horizon) rather than absolute level; reconstruct absolute value
      at serving (`pred = anchor + Δ`) so the regression is not dominated by the level.
- [x] Improve replacement censoring: use `wsmProvDate` change + wheel-age reset + dia-jump consistency
      (single source of truth in the config registry, remove duplicated thresholds in
      `features.py:_boundaries` and `build_lifecycle_segments.py`).
      → Done: `compute_boundaries()` in `build_lifecycle_segments.py` is now the single source of truth
      (`REPLACEMENT_DIA_JUMP_MM = 20.0`, `REPLACEMENT_CONFIRM_SUSTAIN_TOL_MM = 10.0`, confirmed = both-sides
      OR sustained); `features._boundaries` and `build_degradation_substrate.py` delegate to it. Segments
      39,971 → 44,093; missed ≥ 20 mm jumps 4,127 (52%) → **5 (0.06%)**.
- [x] Physics guard, reported not clipped: within a lifecycle segment wear dims are monotone and
      diameter is non-increasing. Backtest reports flag rates (wsmDia 90d/180d bias ≈ 0 after P0.2).
      **Remaining: extend to serving.**
- [x] Conformal prediction intervals — **DONE** in the trajectory-product artefact
      (`trajectory_product_analysis.py`): 80% split-conformal on flange/root/tread, coverage 77–85%
      verified on the temporal test split (§2.4). **Remaining: surface in the API/UI.**
- [x] Re-run `build_serving_models.py` + `build_turn_probability_serving_models.py`, regenerate
      `degradation_benchmark.json` / `fleet_backtest.json`, and record before/after implausibility rates
      in the analysis doc.
      → Done: serving models rebuilt (degradation in Δ-mode, turn-probability on clean boundaries),
      benchmark + fleet backtest regenerated; before/after recorded in
      `ml/docs/ml_correctness_analysis.md` §1.5/§2.1. wsmDia 90d/180d increasing-diameter bias → ≈ 0.
- [x] **Trajectory-product analysis artefact** (`ml/models/phase5/trajectory_product_analysis.py`):
      Δ-metrics side-by-side, residual distribution + noise floor, 80% conformal intervals with
      verified coverage, operational capture@k (turn-within-H), residual panels incl. Loco 37597 via
      serving path. → `ml/models/experiments/v5/trajectory_product_analysis.json` + `.png` (§2.4).

### P0.2b — Trajectory product (flange/root/tread) — honesty layer for the dashboard

Tier 1 (make existing Δ-models honest and usable) — **COMPLETE 2026-08-14**:
- [x] **Chart-data contract** `GET /wheelset/{ws}/trajectory` (trajectory_chart_v1): observed series,
      forecast continuation (anchor + Δ, with `current`/`delta` fields), 80% split-conformal
      low/high bands (from the trajectory artefact), realised residual strip (historical `asof`
      re-anchor), physics flags (reported not clipped), noise floor, and model metadata
      (task / train cutoff / n_train / target_mode).
- [x] **ECharts trajectory panel** (`TrajectoryPanel.tsx`): per-dim chart (flange/root/tread primary,
      dia derived below) with observed line, dashed forecast, conformal band, realised points,
      flags, noise-floor footnote + model meta; as-of re-anchor selector.
- [x] **Δ bug fixed at serving**: serving models regress delta; `service.predict_degradation` and
      `backtest.wheelset_replay` now reconstruct `pred = current + delta` (previously returned raw
      delta as the absolute level, e.g. wsmDia 1053.91 → −8.57). Flags/MAE now compare levels.
- [x] **Delta metrics / noise floor / intervals / residual strip** surfaced in the panel (JSON carries
      them; chart consumes the contract). Noise floor: flange 0.114 / root 0.105 / thread 0.066 mm.
- [x] Dashboard/API surface **delta MAE / R² / ρ** alongside absolute in the fleet backtest view:
      `DegradationDeltaTable` in `BacktestView.tsx` reads the static grid
      (`fleet.degradation.static[dim][H].models.C1_xgb`) and shows ΔMAE / ΔR² / Δρ / n_test
      with positive ΔR² highlighted.
- [x] **Physics flags** at serving time: `predict_degradation` now attaches `implausibility_flag`
      per forecast (wear dims `< current − 0.05 → wear_better_than_current`; dia `> current + 0.001
      → increasing_diameter`); surfaced in the overview API and shown in the trajectory panel.
      Reported, never clipped.

Tier 2 (decision-aligned ranking and remaining life):
- [x] **Operational capture@k**: success = wheelsets that cross an action threshold (or are turned)
      within H days because of flange/root/tread wear (turn-within-H proxy defined in the artefact).
      → Analysis in the trajectory artefact §4; surfaced as `GET /backtest/fleet/capture` and a
      capture@k table on the fleet backtest page (`BacktestView.tsx`). Not a ranking mandate — it
      measures how the predicted-delta top-k list would have caught wheelsets that were actually
      turned within H days (shed behaviour).
- [x] **Time-to-threshold / remaining-life** view: Δ forecast + current value + action limits
      (condemning dia 1016 mm hard stop) → expected days-to-limit with interval. **DONE for the dia
      hard stop (serving-side, no retrain):** `service._time_to_limit` piecewise-linear crossing of
      the 1016 mm condemning limit from the 30/90/180 Δ forecasts; exposed as per-dim `time_to_limit`
      + `time_to_limit_summary` on the trajectory and replay contracts and a days-to-condemning chip
      in the trajectory panel + fleet backtest replay. Subgroup flags ride on the same path (amber
      treatment when the driving dim is flagged). **Remaining:** dia conformal band (interval edges
      null until calibration); flange/root/tread action limits still pending engineering approval.
- [x] **Subgroup stability**: error + coverage by shed / profile class / wheel position / age cohort /
      current wear quantile. Collapse on any large subgroup blocks uniform display. **DONE as an
      analysis + serving/UI policy (no model change):** `subgroup_stability.py` flags 111 collapse
      rows (mostly shed × root/thread); `subgroup_policy.py` matches a wheelset's shed / wear band /
      profile / position / age cohort against `collapse_groups` for each dim×horizon and emits a
      "reduced confidence" badge (amber, dot-dashed forecast) — point forecast shown but not
      decision-grade there. Flange remains the default primary trajectory.

Tier 3 (only after Tier 1–2 are visible):
- [ ] Feature/light-model work if residual analysis shows systematic bias (rate features, exposure,
      boundary residuals). No architecture expansion until residual + interval + operational capture
      are in the UI.

### P0.3 — Honest API surface

- [ ] Every forecast response carries: model version, train cutoff, feature coverage (share of non-NaN
      inputs), implausibility flags, and conformal interval bounds.
- [ ] Serving code loads a `manifest.json`/`features.json` and validates feature schema at load (fail fast,
      not `KeyError` at request time).
- [ ] Dashboard UI renders a forecast only when the P0.2 dia fix is deployed (feature-flagged).

---

## P1 — Data / API foundation

Build the clean backend interface the current UI and the future SLAM frontend will both consume.

### P1.1 — Fleet snapshot dataset

- [ ] Builder script (under `ml/models/phase5/` or `development/dashboard/backend/`) that materialises a
      **fleet snapshot parquet**: one row per wheelset with latest state —
  - [ ] loco number/id, shed, loco type
  - [ ] latest profile state (flange/root/thread/dia), days & distance since turning
  - [ ] per-wheelset degradation forecasts (30/90/180d) + conformal interval widths
  - [ ] P(turn) 30/60/90d
  - [ ] **limiting dimension** (dimension closest to its condemning limit, or highest wear rate)
  - [ ] **risk signals kept separate**: P(turn) AND wear state AND limit proximity (never collapsed into one number)
  - [ ] provenance: feature-store/version stamps so the UI can show staleness
- [ ] Rebuild command documented (and later wired into CI as a scheduled job — see future_work.md).

### P1.2 — Versioned, typed API (the contract of record)

- [ ] Prefix endpoints `/api/v1/...`; keep `/health`.
- [ ] Add endpoints:
  - [ ] `GET /api/v1/fleet/overview` — fleet KPI summary + distributions (profile state, vs limits, turning-risk, shed summary).
  - [ ] `GET /api/v1/fleet/risk` — paginated, filterable, rankable wheelset list (shed, loco type, limiting dimension, risk level; sort by P(turn)/wear rate/limit proximity).
  - [ ] `GET /api/v1/fleet/search?q=` — search by loco number / shed / loco type.
  - [ ] `GET /api/v1/shed/{shed}` — shed-level aggregation.
  - [ ] `GET /api/v1/loco/{loco}` and `GET /api/v1/wheelset/{ws}/overview` (existing, moved under v1).
  - [ ] `GET /api/v1/wheelset/{ws}/lifecycle` — the **chart-data contract** (see P1.3).
  - [ ] `GET /api/v1/wheelset/{ws}/backtest` and `GET /api/v1/backtest/fleet` (existing, moved under v1).
- [ ] Typed Pydantic response models for all new endpoints (extend `schemas.py`).
- [ ] Configuration via environment variables (paths, ports); remove hardcoded `127.0.0.1:8033` and `parents[3]` path math where feasible.
- [ ] **CORS configurable** via env (allow-list), not hardcoded `*` — the host SLAM app controls its own origins.

### P1.3 — Chart-data contract (single source of truth for all plots)

- [ ] Define a versioned JSON contract: `GET /api/v1/wheelset/{ws}/lifecycle?contract=v1` returns everything a chart needs:
  - [ ] measurement series per dimension (observed, with timestamps, quality/segment ids)
  - [ ] segment boundaries + `turn_event` / `replacement` markers (with pre-turn flange/root/tread, `dia_cut`, `pre_dia`, `post_dia`)
  - [ ] forecast continuation per dimension (30/90/180d points) + interval bounds + `model_version` + flags
  - [ ] anchor/latest timestamp, units
- [ ] The Matplotlib export path consumes the SAME contract (a shared backend function builds the series; the renderer is downstream).
  - [ ] Refactor `ml/models/phase5/plot_lifecycle_step.py` to take the contract payload as input (keep a thin CLI wrapper for report generation).
- [ ] **No lifecycle/forecast transformation logic in the frontend** — the React/ECharts layer only renders what the contract provides.

---

## P2 — Fleet + engineering UI

The actual daily tool for engineers. (Work here transfers directly to SLAM.)

### P2.1 — App shell & navigation

- [ ] Sidebar nav: **Fleet** · **Search** · **Validation/Backtest**.
- [ ] Global search box in the topbar (loco number / shed / loco type) with type-ahead from `/fleet/search`.
- [ ] Fleet-health summary header (compact KPIs + distribution chips).

### P2.2 — Fleet view (primary)

- [ ] **Risk-ranked wheelset table** (the main "what do I inspect today" view):
  - columns: loco, wheelset, shed, current profile state, limiting dimension, P(turn) 30/60/90d, wear state / limit proximity, staleness
  - filters: shed, loco type, limiting dimension, risk level
  - sortable by P(turn), wear rate, limit proximity
  - row click → wheelset detail (drill-down)
- [ ] Fleet-health summary above the table:
  - fleet size / wheelsets monitored / data staleness
  - flange/root/thread distributions vs condemning limits
  - turning-risk distribution (share of wheelsets above P(turn) thresholds)
  - shed-level summary (turn rates, data coverage)

### P2.3 — Loco view

- [ ] Loco wheelset table: current state, forecasts, P(turn), limiting dimension, turns count (enhance existing `LocomotiveSummary`).
- [ ] Shed / policy information shown where supported (shed-level turn rates, policy context).
- [ ] Click wheelset → wheelset detail.

### P2.4 — Wheelset detail

- [ ] Interactive lifecycle step plot (see P3.3).
- [ ] Flange/root/tread forecasts with **intervals** + implausibility flags + model-version footnote (replace the plain table).
- [ ] Turning probability cards (retain, add interval/uncertainty context).
- [ ] Confirmed turn table (retain; add `dia_cut`).
- [ ] **Observed vs predicted distinction** clearly surfaced (anchor divider, dashed forecast).
- [ ] Engineering warnings / implausibility flags rendered visibly (not buried in tables).
- [ ] Validation/Backtest page retained, with fleet-level backtest metrics surfaced (`/backtest/fleet`).

### P2.5 — UX states

- [ ] Loading states (skeletons) for fleet table and wheelset detail.
- [ ] Empty states (no data, no results, stale snapshot).
- [ ] Error states with retry.

---

## P3 — UI quality

> Tone: not flashy. Old-age smooth and calm. Inter typography, muted palette, off-white background,
> hairline borders, one restrained accent (indigo), generous whitespace, small labels.

### P3.1 — Design tokens & theme

- [ ] Adopt **Inter** as the UI font (self-hosted `@fontsource/inter` or local asset; no runtime CDN dependency for offline shed use).
- [ ] Define tokens in CSS: background (`#fafafa`-ish off-white), card, hairline border, ink, muted, accent (indigo ~`#4f46e5`), success/warning/danger semantic colors used sparingly.
- [ ] Typography scale: small (11–13px) labels, clear but restrained headings; uppercase micro-labels with letter-spacing for section headers (PostHog feel).
- [ ] Consistent card/table/border/radius/spacing system; no drop shadows (or extremely subtle).

### P3.2 — Component layer

- [ ] Add **ECharts** (`echarts` + a thin React wrapper).
- [ ] Replace hand-rolled SVG `WearTimeline.tsx` with ECharts-backed components.
- [ ] Shared UI primitives: KPI card, table, badge/pill, filter bar, search box, empty state, loading skeleton.
- [ ] Responsive layout (existing 860px breakpoint; verify on field laptops).
- [ ] Keep chart components **data-agnostic**: they consume the chart-data contract objects only (swappable if ECharts is replaced later).
- [ ] Rich tooltips (per-dimension + turn markers with pre-turn flange/root/tread + `dia_cut`).

### P3.3 — Lifecycle + forecast chart (ECharts)

Rendered from `/api/v1/wheelset/{ws}/lifecycle`. Must preserve:
- [ ] **within-segment wear evolution** — wear grows inside each lifecycle segment
- [ ] **discrete turning/reset events** — vertical reset markers, not smoothed across the boundary
- [ ] **pre-turn flange/root/tread + `dia_cut`** in the turn tooltip (from the contract's turn events)
- [ ] **diameter behaviour physically valid** — non-increasing within a segment; never render an invalid increasing-diameter forecast (P0 gate)
- [ ] **observed vs forecast clearly distinguished** — forecast rendered as dashed/muted continuation from the anchor, with interval band; a visual divider at the anchor
- [ ] **interaction** — hover tooltips, zoom/pan on the time axis
- [ ] optional: per-dimension toggles / dual-axis for dia vs wear

### P3.4 — Exports

- [ ] Retain Matplotlib SVG/PNG lifecycle plots as **downloadable/report exports** (rendered server-side from the same contract).
- [ ] Add CSV export of the chart-data contract on the detail page.
- [ ] "Download report" = regenerate the server-side matplotlib figure for the current wheelset/loco.

---

## P4 — Integration readiness (API/deployment contract only)

Make it easy for the SLAM team to consume this as a module. **Authentication and identity are
deferred to the host SLAM application** — we implement none here and make no assumptions about it.

- [ ] Clean API versioning (`/api/v1/...`) — the contract of record for all clients.
- [ ] Environment-based configuration (paths, ports, model dirs, CORS origins) — no hardcoded addresses.
- [ ] CORS configurable via env allow-list (host SLAM app sets its own origins).
- [ ] Predictable response schemas: every endpoint has a typed Pydantic model; errors are consistent
      (`{detail}` FastAPI shape + structured error codes where useful).
- [ ] API documentation: OpenAPI exposed; a short "consume the API" doc (auth boundary note: none here).
- [ ] **No assumptions about authentication** — endpoints work unauthenticated at the module boundary;
      any auth is applied by the SLAM host/proxy.
- [ ] **No SLAM-specific authentication implementation** (no user store, no tokens, no SSO/RBAC).
- [ ] Deployment instructions for the standalone service.
- [ ] Optional, lightweight: **one simple `docker-compose.yml`** (backend + frontend) purely for
      reproducibility. Not a deployment architecture phase — no Kubernetes, no orchestration here.

---

## Environment sync (personal laptop ↔ office PC)

The `ayush` venv is **gitignored**, so each machine has an unshared copy — that is
why "libs I download here aren't there". Fix: the tracked lockfile is the single
source of truth; recreate the venv from it on each machine.

```powershell
# (1) one-time on a new machine — from repo root
#     requires Python >= 3.12 (the pinned lock needs numpy 2.5 / pandas 3.0)
python -m venv ayush
ayush\Scripts\python.exe -m pip install --upgrade pip
ayush\Scripts\python.exe -m pip install -e .          # installs pyproject.toml deps + `wheel-dashboard` launcher

# (2) whenever you add/upgrade a library — commit the change to BOTH:
ayush\Scripts\python.exe -m pip install <pkg>
ayush\Scripts\python.exe -m pip freeze > ml\environment\requirements-lock.txt
#    then also update the pinned `dependencies` list in pyproject.toml (same pins);
#    commit both. On the other machine: re-run (1) install step only.
```

- `pyproject.toml` (repo root) = single reproducible install: pinned deps + editable `dashboard`
  package + a `wheel-dashboard` console launcher that runs uvicorn with env-driven
  `WHEEL_HOST`/`WHEEL_PORT`/`WHEEL_RELOAD` (no PYTHONPATH fiddling — `_paths.py` injects the `ml`
  root). The lockfile (`requirements-lock.txt`) stays as the exact `pip freeze` record; the two
  must not drift.
- Backend run (from repo root): `ayush\Scripts\wheel-dashboard`  → http://127.0.0.1:8033
- Frontend: `npm install` (committed `package-lock.json`), then `npm run dev`.
- Existing models/datasets (parquets, joblib, JSON) are committed/versioned under
  `ml/` — pull to get them; no library state is ever carried in git.

---

## Deferred (see `future_work.md`)

- Kubernetes, microservices, cloud infra, observability stack.
- SSO, RBAC, user management, secrets infrastructure → **owned by the SLAM host**.
- CI/CD pipelines, model registry, drift monitoring, orchestration, dbt.

---

## Priority order

1. **P0** ML correctness (gate) — P0.2 (boundaries + Δ-model) done; P0.2b trajectory-product honesty
   layer (delta metrics, residual strip, noise floor, intervals, physics flags, operational capture@k,
   then subgroup stability / time-to-threshold).
2. **P1** Data/API foundation — typed, versioned contract for the current UI and SLAM.
3. **P2** Fleet + engineering UI — the daily tool (highest-value transferable work).
4. **P3** UI quality — ECharts, design system, tooltips, exports (overlaps with P2).
5. **P4** Integration readiness — API/deployment contract only; auth deferred to SLAM host.

Product framing (owner-documented): the engineer-facing deliverable is the **flange / root / tread
trajectory** (expected wear over 30/90/180d) with **confidence, residual evidence, and time-to-action
derived from it**. Diameter is a derived diagnostic (cut rule + condemning limit) and P(turn) is a
prioritisation launcher — neither replaces the trajectory.
