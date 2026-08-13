# Future Work — Enterprise Hygiene (Deferred)

> Status: **NOT in the current phase.** These are the enterprise-level issues raised in the
> senior review (see `dashboard_roadmap.md` for what IS being done now). They are captured here
> so they are not lost; tick items off as they get picked up. They make the project harder to
> change, but intentionally deferred to avoid blocking dashboard / ML correctness work.
>
> Last review: 2026-08-13

---

## 1. Repository & version-control hygiene

- [ ] Reduce `.git` size (currently ~1.6 GB, 2039 tracked files).
- [ ] Move tracked binaries out of git: 213 `.joblib`, 277 `.parquet`, 83 `.png`, 4 `.docx`, 4 `.ipynb` (with outputs), 2 `.xlsx`.
  - [ ] Datasets/artifacts → DVC or Git LFS (or an artifact store / model registry).
  - [ ] Notebooks committed without executed outputs (nb-clean / jupytext) or moved out.
  - [ ] Add `*.parquet`, `*.joblib`, `*.png`, `*.svg`, `*.docx`, `*.xlsx`, `*.ipynb` guards in `.gitignore`.
- [ ] Remove/ignore the duplicate copy of the model code at repo-root `models/` (`phase3c|phase3d|phase3e|phase5`, untracked but on disk with `__pycache__`). Single source of truth is `ml/models/`.
- [ ] Remove the `ayush/` virtualenv (~500 MB) from the repo root; keep envs out of the workspace or under an ignored path.
- [ ] Clean up `.gitignore`: stray `.ayush` entry, duplicated files at root vs `ml/`, consolidate into one.
- [ ] Move large raw datasets (`data/bronze`, `data/silver`, `data/gold`) to a real data platform (object store / Delta lake) with a catalog; keep repo lean.

## 2. CI/CD

- [ ] Add CI pipeline (GitHub Actions or equivalent): test job + lint/format + build jobs for backend and frontend.
- [ ] Add lint + formatter config and enforce in CI: ruff (Python), eslint/prettier (TS), mypy/pyright type check.
- [ ] Add pre-commit hooks (lint, format, secrets scan, no-large-files).
- [ ] Add secret scanning (e.g. gitleaks) to CI.
- [ ] Make tests hermetic so they run on a fresh clone (see §4).

## 3. Packaging & reproducibility

- [ ] Add `pyproject.toml`; make `ml/` and `development/` installable packages.
- [ ] Kill the runtime `sys.path` hacks (`development/dashboard/backend/_paths.py`) in favour of proper imports/packages.
- [ ] Single dependency source of truth: reconcile `ml/requirements.txt` (16 pkgs) vs `ml/environment/requirements-lock.txt` (24 pkgs) — catboost/lightgbm/plotly/graphviz only in one.
- [ ] Pin everything with a hash-locked lockfile (uv or poetry): seaborn, nbformat, requests are unpinned today.
- [ ] Enforce dependency version pinning in CI.

## 4. Test coverage

- [ ] Replace tests that read real parquet from disk with small committed fixtures (currently tests cannot run on a fresh clone).
- [ ] Add unit tests for: feature extraction (`features.py`), serving models, the FastAPI backend, the backtest engine, the feature-store builder.
- [ ] Add contract tests for the chart-data API (see `dashboard_roadmap.md` P1).
- [ ] Add golden/snapshot tests for ML correctness gates (implausibility rates, replacement contamination audit).

## 5. Security & identity

> Identity boundary: this dashboard is a future module inside the **SLAM ecosystem**. SSO, RBAC,
> user management and secrets infrastructure are **owned by the SLAM host application** — do not build
> an identity stack here (see `dashboard_roadmap.md` P4). The items below are module-level hygiene that
> remains on our side.

- [ ] Fix path traversal in `development/dashboard/backend/main.py` `loco_plots` (user-supplied `loco_number` interpolated into a filesystem path).
- [ ] Replace CORS `allow_origins=["*"]` with an env-configurable allow-list.
- [ ] Add rate limiting / request validation on public endpoints.
- [ ] Move secrets to a vault/env manager (`.env` is gitignored but handling is ad-hoc).
- [ ] (Deferred to SLAM host) SSO, RBAC, user management, secrets infrastructure.

## 6. ML governance & platform

- [ ] Adopt a model registry (e.g. MLflow) for training, evaluation and serving artifacts; replace ad-hoc `experiments/v1..v5` folders + oversized `.joblib` copies.
- [ ] Versioned, schema-checked model loading in the API; input/output contract validation at the edge.
- [ ] Drift / shadow / rollback strategy for serving models; prediction logging and monitoring.
- [ ] Data versioning + lineage end-to-end (dataset hash → model → evaluation).
- [ ] Pipeline orchestration (Airflow/Dagster/Prefect) for bronze→silver→gold→feature-store rebuilds; today it is manual script runs.
- [ ] Move SQL (currently `.txt` in `supported_doc/`) into governed, versioned migrations (dbt / Liquibase).

## 7. Frontend engineering

- [ ] Generate the API client + types from OpenAPI instead of hand-maintaining `types.ts`.
- [ ] Add frontend tests + lint.
- [ ] Add a build-level schema check between Pydantic response models and the generated TS types.

## 8. Docs / governance

- [ ] Single living status index; today there are multiple self-described sources of truth (README, `docs/current_place.md`, `docs/project_status_table.md`, `docs/plan.md`) that have drifted from code.
