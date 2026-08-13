# development

Product / application code. ML model research, feature extraction, substrates and
serving artifacts live under `ml/`; this folder holds the user-facing dashboard
that reads from them.

## Dashboard (Layer 5)

FastAPI backend + React/Vite frontend.

### Layout
- `dashboard/backend/` - FastAPI app + validation/backtest engine:
  - `_paths.py` - bootstrap that resolves the `ml/` root and adds it to `sys.path`
    (the app imports the ML feature extractor / serving models from `ml/`).
  - `main.py` - uvicorn app; endpoints under `/loco`, `/wheelset`, `/backtest`.
  - `service.py` - loco summary, wheelset history, degradation + P(turn) prediction.
  - `backtest.py` - strict point-in-time wheelset replay + fleet metrics.
  - `schemas.py` - pydantic response models.
- `dashboard/frontend/` - React/Vite SPA (dev server proxies `/api/*` -> backend).

### Run
Backend (uvicorn on 127.0.0.1:8033):
```
$env:PYTHONPATH="<repo>\development;<repo>\ml"
& "<repo>\ml\.ayush\Scripts\python.exe" -m uvicorn dashboard.backend.main:app --host 127.0.0.1 --port 8033
```
(run with cwd = `<repo>\development`, or point PYTHONPATH at both `development` and `ml`)

Frontend (vite dev on http://127.0.0.1:5173):
```
npm run dev
```
(run with cwd = `<repo>\development\dashboard\frontend`)

### Validation endpoints
- `GET /wheelset/{ws}/backtest?asof=YYYY-MM-DD` - replay a single wheelset at a
  historical as-of date; freeze features point-in-time, compare degradation
  forecasts and P(turn) probabilities against the actual future observations.
  Implausibility flags reported (never clipped); raw P(turn) exposed unrounded.
- `GET /backtest/fleet` - fleet-level temporal metrics (ROC-AUC, PR-AUC, Brier,
  ECE, capture@top 5/10%) + model-vs-actual implausibility diagnostics.
