"""Layer 5 dashboard - FastAPI backend.

Endpoints (locomotive-first):
  GET /loco/{loco_number}                loco summary + wheelset table
  GET /wheelset/{ws}/overview            current state + C1 forecasts + P(turn)
  GET /wheelset/{ws}/history             measurement stream + confirmed turns

Model outputs are estimates from trained models, not engineering mandates:
degradation forecasts predict profile state evolution; P(turn) is historical
maintenance behaviour (not "must be turned").
"""
from __future__ import annotations

import time

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    FleetBacktest, LocomotiveSummary, WheelsetDetail, WheelsetReplay,
)
from . import backtest, service

app = FastAPI(
    title="Wheel Lifecycle Dashboard (Layer 5)",
    version="0.1.0",
    description=("Locomotive-first dashboard: wheel profile state, degradation "
                 "forecasts (30/90/180d) and turning probability (30/60/90d)."),
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "t": time.time()}


@app.get("/loco/{loco_number}", response_model=LocomotiveSummary)
def loco(loco_number: str) -> LocomotiveSummary:
    data = service.loco_summary(loco_number)
    if not data["wheelsets"]:
        raise HTTPException(status_code=404,
                            detail=f"no wheelsets found for loco {loco_number}")
    return LocomotiveSummary(**data)


@app.get("/wheelset/{ws}/overview", response_model=WheelsetDetail)
def wheelset_overview(ws: int) -> WheelsetDetail:
    hist = service.wheelset_history(ws)
    if not hist["measurements"]:
        raise HTTPException(status_code=404, detail=f"no data for wheelset {ws}")
    deg = service.predict_degradation(ws)
    pt = service.predict_pturn(ws)
    latest = hist["measurements"][-1]["measurement_timestamp"]
    loco_n = None
    wes = service.load_wes()
    m = wes[wes["wheelset_equipment_id"] == ws]
    if not m.empty:
        loco_n = str(m.iloc[-1]["LomNumber"]) if pd_notna(m.iloc[-1]["LomNumber"]) else None
    return WheelsetDetail(
        wheelset_equipment_id=ws,
        loco_number=loco_n,
        latest_measurement=latest,
        forecasts=deg["forecasts"],
        turn_probabilities=pt["probabilities"],
        turns=hist["turns"],
        measurements=hist["measurements"],
    )


def pd_notna(v):
    try:
        import pandas as pd
        return pd.notna(v)
    except ImportError:
        return v is not None


@app.get("/wheelset/{ws}/backtest", response_model=WheelsetReplay)
def wheelset_backtest(ws: int, asof: str = Query(..., description="as-of date YYYY-MM-DD")):
    try:
        anchor = pd.Timestamp(asof)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid as-of date: {asof}") from exc
    res = backtest.wheelset_replay(ws, anchor)
    if res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return WheelsetReplay(**{k: res[k] for k in WheelsetReplay.model_fields})


@app.get("/backtest/fleet", response_model=FleetBacktest)
def fleet_backtest():
    data = backtest.fleet_metrics()
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return FleetBacktest(**data)