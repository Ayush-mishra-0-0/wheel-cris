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
    FleetBacktest, LocomotiveSummary, OperationalCapture, TrajectoryContract,
    WheelsetDetail, WheelsetReplay,
)
from . import backtest, service
import base64
import io

# plotting helper (phase5)
from models.phase5 import plot_lifecycle_step

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


@app.get("/wheelset/{ws}/trajectory", response_model=TrajectoryContract)
def wheelset_trajectory(ws: int, asof: str | None = Query(None, description="re-anchor at YYYY-MM-DD")):
    """Chart-data contract for the trajectory panel (trajectory_chart_v1).

    Wear dims (flange/root/tread) are the primary product; wsmDia is derived.
    Forecast = anchor + delta; 80% conformal bands + noise floor come from the
    trajectory artefact; physics flags are reported, never clipped. Realised
    residuals appear when `asof` re-anchors at a historical measurement.
    """
    anchor = pd.Timestamp(asof) if asof else None
    data = service.trajectory(ws, anchor)
    if not data["dims"]:
        raise HTTPException(status_code=404, detail=f"no data for wheelset {ws}")
    return TrajectoryContract(**data)


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


@app.get("/backtest/fleet/capture", response_model=OperationalCapture)
def fleet_capture():
    """Operational capture@k for wear-dim turn-within-H, from the trajectory artefact.

    Not a ranking mandate: it measures how well ranking by predicted delta finds
    wheelsets that were actually turned within H days (shed behaviour), so an
    engineer knows what the top-k inspection list would have caught.
    """
    return OperationalCapture(**service.operational_capture())


@app.get("/loco/{loco_number}/plots")
def loco_plots(loco_number: str) -> dict:
    """Generate lifecycle step PNGs for all wheelsets on a loco and return base64 images.

    This calls the Phase 5 plotting utility which writes PNGs to its report
    output directory; we read them and return base64-encoded bytes in JSON.
    """
    turns, wes = plot_lifecycle_step.load_data()
    # match loco number in WES (LomNumber may be int or str)
    w = wes[wes["LomNumber"].astype(str) == str(loco_number)]
    if w.empty:
        raise HTTPException(status_code=404, detail=f"no wheelsets found for loco {loco_number}")
    wheelsets = sorted(w["wheelset_equipment_id"].unique())
    images: dict = {}
    from pathlib import Path
    outdir = plot_lifecycle_step.OUTPUT_DIR
    svgs: dict = {}
    for ws in wheelsets:
        svg_name = f"lifecycle_step_loco_{loco_number}_wheelset_{ws}.svg"
        svg_path = outdir / svg_name
        if svg_path.exists():
            try:
                with open(svg_path, "r", encoding="utf-8") as fh:
                    svgs[str(ws)] = fh.read()
                continue
            except Exception as exc:
                svgs[str(ws)] = f"error reading svg file: {exc}"
                continue

        # fallback to PNG if SVG missing or read fails
        img_name = f"lifecycle_step_loco_{loco_number}_wheelset_{ws}.png"
        img_path = outdir / img_name
        if img_path.exists():
            try:
                with open(img_path, "rb") as fh:
                    images[str(ws)] = base64.b64encode(fh.read()).decode("ascii")
                continue
            except Exception as exc:
                images[str(ws)] = f"error reading png file: {exc}"
                # continue to attempt generation

        # fallback: generate plot on-demand (will create both png and svg if possible)
        measurements = wes[wes["wheelset_equipment_id"] == ws].copy()
        events = turns[turns["wheelset_equipment_id"] == ws].copy()
        try:
            p = plot_lifecycle_step.plot_wheelset(int(ws), str(loco_number), measurements, events, outdir)
            # prefer svg we just tried to produce
            svg_p = Path(p).with_suffix('.svg')
            if svg_p.exists():
                with open(svg_p, 'r', encoding='utf-8') as fh:
                    svgs[str(ws)] = fh.read()
            else:
                with open(p, 'rb') as fh:
                    images[str(ws)] = base64.b64encode(fh.read()).decode('ascii')
        except Exception as exc:
            images[str(ws)] = f"error generating plot: {exc}"
    return {"loco": loco_number, "images": images, "svgs": svgs}