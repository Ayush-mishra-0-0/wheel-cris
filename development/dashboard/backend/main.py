"""Layer 5 dashboard - FastAPI backend.

The contract of record is the versioned API in api_v1.py (/api/v1/...).
This module assembles the app: /health (unversioned infra) + the v1 router,
plus unversioned aliases so existing consumers keep working during migration.
"""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import service
from .api_v1 import router as v1_router
from .config import CORS_ORIGINS

app = FastAPI(
    title="Wheel Lifecycle Dashboard (Layer 5)",
    version="0.1.0",
    description=("Locomotive-first dashboard: wheel profile state, degradation "
                 "forecasts (30/90/180d) and turning probability (30/60/90d)."),
)

# Fail fast: a broken serving artifact set should surface at startup, not as a
# KeyError on the first forecast request.
_validation_warnings: list[str] = service.validate_serving()

# CORS is env-configurable (WHEEL_CORS_ORIGINS), never hard-coded "*".
app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "t": time.time(),
            "validation": {"warnings": _validation_warnings}}


# Versioned API (the contract of record).
app.include_router(v1_router)


# ---------------------------------------------------------------------------
# Unversioned aliases (deprecated) - thin redirects to the same handlers so
# old URLs keep working during migration.
# ---------------------------------------------------------------------------
from fastapi import HTTPException, Query  # noqa: E402

from .schemas import (  # noqa: E402
    Capabilities, FleetBacktest, FleetOverview, LocomotiveSummary, OperationalCapture,
    TrajectoryContract, WheelsetDetail, WheelsetReplay,
)
from .api_v1 import (  # noqa: E402
    config as _config,
    fleet_capture as _fleet_capture,
    fleet_backtest as _fleet_backtest,
    fleet_overview as _fleet_overview,
    fleet_risk as _fleet_risk,
    fleet_search as _fleet_search,
    loco as _loco,
    loco_plots as _loco_plots,
    shed_overview as _shed_overview,
    wheelset_backtest as _wheelset_backtest,
    wheelset_lifecycle as _wheelset_lifecycle,
    wheelset_overview as _wheelset_overview,
    wheelset_trajectory as _wheelset_trajectory,
)


@app.get("/config", response_model=Capabilities)
def config_legacy():
    return _config()


@app.get("/loco/{loco_number}", response_model=LocomotiveSummary)
def loco_alias(loco_number: str):
    return _loco(loco_number)


@app.get("/wheelset/{ws}/overview", response_model=WheelsetDetail)
def wheelset_overview_alias(ws: int):
    return _wheelset_overview(ws)


@app.get("/wheelset/{ws}/trajectory", response_model=TrajectoryContract)
def wheelset_trajectory_alias(ws: int, asof: str | None = Query(None)):
    return _wheelset_trajectory(ws, asof)


@app.get("/wheelset/{ws}/lifecycle", response_model=TrajectoryContract)
def wheelset_lifecycle_alias(ws: int, asof: str | None = Query(None), contract: str = Query("v1")):
    return _wheelset_lifecycle(ws, asof, contract)


@app.get("/wheelset/{ws}/backtest", response_model=WheelsetReplay)
def wheelset_backtest_alias(ws: int, asof: str = Query(...)):
    return _wheelset_backtest(ws, asof)


@app.get("/backtest/fleet", response_model=FleetBacktest)
def fleet_backtest_alias():
    return _fleet_backtest()


@app.get("/backtest/fleet/capture", response_model=OperationalCapture)
def fleet_capture_alias():
    return _fleet_capture()


@app.get("/loco/{loco_number}/plots")
def loco_plots_alias(loco_number: str):
    return _loco_plots(loco_number)


@app.get("/fleet/overview", response_model=FleetOverview)
def fleet_overview_alias():
    return _fleet_overview()


@app.get("/fleet/risk", response_model=dict)
def fleet_risk_alias(shed: str | None = None, loco_type: str | None = None,
                     limiting_dim: str | None = None, risk_level: str | None = None,
                     sort_by: str = "pturn_90d", descending: bool = True,
                     page: int = 1, page_size: int = 50):
    return _fleet_risk(shed, loco_type, limiting_dim, risk_level,
                       sort_by, descending, page, page_size)


@app.get("/fleet/search", response_model=dict)
def fleet_search_alias(q: str = Query(...)):
    return _fleet_search(q)


@app.get("/shed/{shed}", response_model=dict)
def shed_overview_alias(shed: str):
    return _shed_overview(shed)
