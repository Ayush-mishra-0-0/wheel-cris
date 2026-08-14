"""Layer 5 dashboard - versioned API (the contract of record).

All product endpoints live under /api/v1/... (P1.2). The unversioned paths
in main.py are thin aliases over the same handlers so nothing breaks while
consumers migrate to the versioned contract.
"""
from __future__ import annotations

import base64
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path

from .schemas import (
    Capabilities, FleetBacktest, FleetOverview, FleetRiskResponse, FleetSearchResponse,
    LocomotiveSummary, OperationalCapture, ShedOverview,
    TrajectoryContract, WheelsetDetail, WheelsetReplay,
)
from . import backtest, service

router = APIRouter(prefix="/api/v1")

# plotting helper (phase5)
from models.phase5 import plot_lifecycle_step


@router.get("/config", response_model=Capabilities, tags=["meta"])
def config() -> Capabilities:
    """Feature flags + serving model identity for the UI.

    `p0_2_dia_fix` gates forecast rendering: the UI shows degradation
    forecasts only when the serving models are in delta mode (P0.2 fix
    deployed). Read-only; the flag is derived from the artifacts on disk.
    """
    caps = service.capabilities()
    caps["validation"] = {"warnings": _validation_warnings()}
    return Capabilities(**caps)


@lru_cache(maxsize=1)
def _validation_warnings() -> list[str]:
    # captured at app import by main.py (validate_serving is fail-fast at boot)
    from .main import _validation_warnings as warnings
    return warnings


@router.get("/fleet/overview", response_model=FleetOverview, tags=["fleet"])
def fleet_overview() -> FleetOverview:
    """Fleet KPI summary + distributions (profile state, vs limits, turning-risk, sheds)."""
    data = service.fleet_overview()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return FleetOverview(**data)


@router.get("/fleet/risk", response_model=FleetRiskResponse, tags=["fleet"])
def fleet_risk(
    shed: str | None = Query(None, description="filter by shed_any"),
    loco_type: str | None = Query(None, description="filter by loco type"),
    limiting_dim: str | None = Query(None, description="filter by limiting dimension"),
    risk_level: str | None = Query(None, description="pturn | condemning | wear"),
    sort_by: str = Query("pturn_90d", description="column to sort by"),
    descending: bool = Query(True, description="sort descending"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> FleetRiskResponse:
    """Paginated, filterable, rankable wheelset risk table (P2.2 fleet view)."""
    data = service.fleet_risk(shed=shed, loco_type=loco_type, limiting_dim=limiting_dim,
                              risk_level=risk_level, sort_by=sort_by,
                              descending=descending, page=page, page_size=page_size)
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return FleetRiskResponse(**data)


@router.get("/fleet/search", response_model=FleetSearchResponse, tags=["fleet"])
def fleet_search(q: str = Query(..., description="loco number / shed / loco type")) -> FleetSearchResponse:
    """Search loco number / shed / loco type from the fleet snapshot."""
    data = service.fleet_search(q)
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return FleetSearchResponse(**data)


@router.get("/shed/{shed}", response_model=ShedOverview, tags=["fleet"])
def shed_overview(shed: str) -> ShedOverview:
    """Shed-level aggregation (wheelset count, limiting dims, turn risk, staleness)."""
    data = service.shed_overview(shed)
    if data.get("error") and data.get("n_wheelsets", 0) == 0:
        raise HTTPException(status_code=404, detail=f"no wheelsets found for shed {shed}")
    return ShedOverview(**data)


@router.get("/loco/{loco_number}", response_model=LocomotiveSummary, tags=["loco"])
def loco(loco_number: str) -> LocomotiveSummary:
    data = service.loco_summary(loco_number)
    if not data["wheelsets"]:
        raise HTTPException(status_code=404,
                            detail=f"no wheelsets found for loco {loco_number}")
    return LocomotiveSummary(**data)


@router.get("/wheelset/{ws}/overview", response_model=WheelsetDetail, tags=["wheelset"])
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
        loco_n = str(m.iloc[-1]["LomNumber"]) if _pd_notna(m.iloc[-1]["LomNumber"]) else None
    return WheelsetDetail(
        wheelset_equipment_id=ws,
        loco_number=loco_n,
        latest_measurement=latest,
        forecasts=deg["forecasts"],
        model=deg.get("model"),
        feature_coverage=deg.get("feature_coverage"),
        turn_probabilities=pt["probabilities"],
        turns=hist["turns"],
        measurements=hist["measurements"],
    )


def _pd_notna(v):
    return pd.notna(v)


@router.get("/wheelset/{ws}/trajectory", response_model=TrajectoryContract, tags=["wheelset"])
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


@router.get("/wheelset/{ws}/lifecycle", response_model=TrajectoryContract, tags=["wheelset"])
def wheelset_lifecycle(ws: int, asof: str | None = Query(None, description="re-anchor at YYYY-MM-DD"),
                       contract: str = Query("v1", description="chart-data contract version")):
    """The chart-data contract (P1.3): everything a chart needs in one payload.

    Currently served by the same backend builder as /trajectory; P1.3 makes
    the Matplotlib export path consume this identical payload.
    """
    if contract != "v1":
        raise HTTPException(status_code=400, detail=f"unknown contract version: {contract}")
    anchor = pd.Timestamp(asof) if asof else None
    data = service.trajectory(ws, anchor)
    if not data["dims"]:
        raise HTTPException(status_code=404, detail=f"no data for wheelset {ws}")
    return TrajectoryContract(**data)


@router.get("/wheelset/{ws}/backtest", response_model=WheelsetReplay, tags=["backtest"])
def wheelset_backtest(ws: int, asof: str = Query(..., description="as-of date YYYY-MM-DD")):
    try:
        anchor = pd.Timestamp(asof)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid as-of date: {asof}") from exc
    res = backtest.wheelset_replay(ws, anchor)
    if res.get("error"):
        raise HTTPException(status_code=404, detail=res["error"])
    return WheelsetReplay(**{k: res[k] for k in WheelsetReplay.model_fields})


@router.get("/backtest/fleet", response_model=FleetBacktest, tags=["backtest"])
def fleet_backtest():
    data = backtest.fleet_metrics()
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return FleetBacktest(**data)


@router.get("/backtest/fleet/capture", response_model=OperationalCapture, tags=["backtest"])
def fleet_capture():
    """Operational capture@k for wear-dim turn-within-H, from the trajectory artefact.

    Not a ranking mandate: it measures how well ranking by predicted delta finds
    wheelsets that were actually turned within H days (shed behaviour), so an
    engineer knows what the top-k inspection list would have caught.
    """
    return OperationalCapture(**service.operational_capture())


@router.get("/loco/{loco_number}/plots", tags=["loco"])
def loco_plots(loco_number: str) -> dict:
    """Generate lifecycle step PNGs for all wheelsets on a loco and return base64 images.

    This calls the Phase 5 plotting utility which writes PNGs to its report
    output directory; we read them and return base64-encoded bytes in JSON.
    """
    turns, wes = plot_lifecycle_step.load_data()
    w = wes[wes["LomNumber"].astype(str) == str(loco_number)]
    if w.empty:
        raise HTTPException(status_code=404, detail=f"no wheelsets found for loco {loco_number}")
    wheelsets = sorted(w["wheelset_equipment_id"].unique())
    images: dict = {}
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

        img_name = f"lifecycle_step_loco_{loco_number}_wheelset_{ws}.png"
        img_path = outdir / img_name
        if img_path.exists():
            try:
                with open(img_path, "rb") as fh:
                    images[str(ws)] = base64.b64encode(fh.read()).decode("ascii")
                continue
            except Exception as exc:
                images[str(ws)] = f"error reading png file: {exc}"

        measurements = wes[wes["wheelset_equipment_id"] == ws].copy()
        events = turns[turns["wheelset_equipment_id"] == ws].copy()
        try:
            p = plot_lifecycle_step.plot_wheelset(int(ws), str(loco_number), measurements, events, outdir)
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
