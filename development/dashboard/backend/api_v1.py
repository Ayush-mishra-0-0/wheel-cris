"""Layer 5 dashboard - versioned API (the contract of record).

All product endpoints live under /api/v1/... (P1.2). The unversioned paths
in main.py are thin aliases over the same handlers so nothing breaks while
consumers migrate to the versioned contract.
"""
from __future__ import annotations

import base64
import csv
import io
import tempfile
from functools import lru_cache
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path

from .schemas import (
    Capabilities, DispositionCreate, DispositionRecord, DispositionSummary,
    FleetBacktest, FleetLocos, FleetOverview, FleetRiskResponse,
    FleetSearchResponse, FleetWorklistResponse, LocomotiveSummary,
    LocoWheelsetTable, ModelHealth, OperationalCapture, ShedOverview,
    TrajectoryContract, WheelAttribution, WheelsetDetail, WheelsetReplay,
)
from . import backtest, service
from .config import ENABLE_LEGACY_PLOTS

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
    max_staleness_days: int | None = Query(365, ge=0,
                                           description="hide wheelsets not measured within N days (measurement recency, not proven fit); null = show all"),
    days_to_condemning_max: int | None = Query(None, ge=1,
                                               description="action queue: keep wheelsets ≤N days from the approved 1016 mm dia hard stop"),
    pturn_min: float | None = Query(None, ge=0, le=1,
                                    description="action queue: keep wheelsets with 90d P(turn) ≥ this fraction (e.g. 0.05 = 5%)"),
) -> FleetRiskResponse:
    """Paginated, filterable, rankable wheelset risk table (P2.2 fleet view)."""
    data = service.fleet_risk(shed=shed, loco_type=loco_type, limiting_dim=limiting_dim,
                              risk_level=risk_level, sort_by=sort_by,
                              descending=descending, page=page, page_size=page_size,
                              max_staleness_days=max_staleness_days,
                              days_to_condemning_max=days_to_condemning_max,
                              pturn_min=pturn_min)
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


@router.get("/fleet/worklist", response_model=FleetWorklistResponse, tags=["fleet"])
def fleet_worklist(
    k: int = Query(10, ge=1, le=100, description="top-k wheelsets per shed"),
    shed: str | None = Query(None, description="restrict to one shed"),
    max_staleness_days: int | None = Query(365, ge=0),
) -> FleetWorklistResponse:
    """Capacity-aware morning worklist: top-k per shed by calibrated 90d P(turn).

    Each shed gets at most `k` rows so one busy shed cannot crowd out the rest
    of the fleet. Prioritisation aid, not a turning instruction (contract §8).
    """
    data = service.fleet_worklist(k=k, shed=shed, max_staleness_days=max_staleness_days)
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return FleetWorklistResponse(**data)


@router.get("/fleet/dispositions/summary", response_model=DispositionSummary, tags=["fleet"])
def disposition_summary() -> DispositionSummary:
    """Fleet-wide engineer-disposition counts (last 30d vs all time)."""
    return DispositionSummary(**service.disposition_summary())


@router.get("/fleet/trend", tags=["fleet"])
def fleet_trend():
    """Fleet KPI trend across archived snapshots (oldest -> newest).

    One point per archived snapshot date; the live snapshot joins when its
    build date differs. Fewer than two points = history still collecting.
    """
    return service.fleet_trend()


@router.post("/wheelset/{ws}/disposition", response_model=DispositionRecord, tags=["wheelset"])
def record_disposition(ws: int, body: DispositionCreate) -> DispositionRecord:
    """Record an engineer decision on this wheelset (turn/inspect/defer/no_action).

    Closes the recommendation loop: accepted or rejected, every decision is
    logged with the snapshot context the engineer saw (calibrated P(turn),
    decile, snapshot build time). This log is the labelled dataset for
    action-quality evaluation.
    """
    try:
        rec = service.record_disposition(ws, body.action, body.note, body.loco_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return DispositionRecord(**rec)


@router.get("/wheelset/{ws}/dispositions", response_model=list[DispositionRecord], tags=["wheelset"])
def dispositions_for(ws: int) -> list[DispositionRecord]:
    """Disposition history for one wheelset (oldest first)."""
    return [DispositionRecord(**r) for r in service.dispositions_for(ws)]


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
    if not data["wheelsets"] and not data.get("wheelsets_all"):
        raise HTTPException(status_code=404,
                            detail=f"no wheelsets found for loco {loco_number}")
    return LocomotiveSummary(**data)


@router.get("/loco/{loco_number}/wheelsets", response_model=LocoWheelsetTable, tags=["loco"])
def loco_wheelset_table(loco_number: str) -> LocoWheelsetTable:
    """Enhanced loco wheelset table (P2.3): current state + 90d forecasts +
    P(turn) + limiting dimension per wheelset (snapshot-backed when available).
    """
    data = service.loco_wheelset_table(loco_number)
    if not data["wheelsets"] and not data.get("wheelsets_all"):
        raise HTTPException(status_code=404,
                            detail=f"no wheelsets found for loco {loco_number}")
    return LocoWheelsetTable(**data)


@router.get("/model/health", response_model=ModelHealth, tags=["meta"])
def model_health() -> ModelHealth:
    """Model-health panel: per-dim x horizon prediction quality + P(turn)

    reliability. Read-only self-assessment from the committed benchmark
    artifacts (trajectory_product_analysis.json, turn_probability_benchmark.json);
    nothing is recomputed live.
    """
    return ModelHealth(**service.model_health())


@router.get("/fleet/locos", response_model=FleetLocos, tags=["fleet"])
def fleet_locos() -> FleetLocos:
    """Ordered list of all locomotives in the snapshot for the loco switcher."""
    data = service.fleet_locos()
    return FleetLocos(**data)


@router.get("/wheelset/{ws}/attribution", response_model=WheelAttribution | None, tags=["wheelset"])
def wheelset_attribution(ws: int, target: str = "turn") -> WheelAttribution | None:
    """Phase 4 per-wheel attribution (likely contributors) for a scored wheelset.

    target="turn" (shipping) or "root" (exploratory - sparse; see the Phase 4
    report). Attribution is model attribution, never "cause" (contract §8).
    Returns 204/None when the wheelset is not in the Phase 4 scored batch.
    """
    if target not in ("turn", "root"):
        raise HTTPException(status_code=422, detail="target must be 'turn' or 'root'")
    a = service.turn_attribution(ws, target=target)
    if a is None:
        raise HTTPException(status_code=404,
                            detail=f"wheelset {ws} not in the phase 4 scored batch ({target})")
    return WheelAttribution(**a)


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


def _trajectory_contract_to_csv(contract: dict) -> bytes:
    """Convert TrajectoryContract to CSV format.
    
    Format: one row per observation with columns:
    dim, timestamp, value, segment_index, turn_event, replacement, ... forecast data
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "dim", "timestamp", "value", "segment_index", "turn_event", "replacement",
        "forecast_30d", "forecast_90d", "forecast_180d",
        "low_30d", "low_90d", "low_180d",
        "high_30d", "high_90d", "high_180d"
    ])
    
    # Collect all observations by dimension
    for d in contract.get("dims", []):
        dim = d.get("dim")
        observed = d.get("observed", [])
        forecasts = d.get("forecasts", [])
        
        # Index forecasts by horizon (30/90/180d)
        fc_by_horizon = {}
        for fc in forecasts:
            fc_by_horizon[int(fc["horizon"])] = fc
        
        # Write observation rows
        for obs in observed:
            row = [
                dim,
                obs.get("ts", ""),
                obs.get("value", ""),
                obs.get("segment_index", ""),
                obs.get("turn_event", False),
                obs.get("replacement", False),
                fc_by_horizon.get(30, {}).get("predicted", ""),
                fc_by_horizon.get(90, {}).get("predicted", ""),
                fc_by_horizon.get(180, {}).get("predicted", ""),
                fc_by_horizon.get(30, {}).get("low", ""),
                fc_by_horizon.get(90, {}).get("low", ""),
                fc_by_horizon.get(180, {}).get("low", ""),
                fc_by_horizon.get(30, {}).get("high", ""),
                fc_by_horizon.get(90, {}).get("high", ""),
                fc_by_horizon.get(180, {}).get("high", ""),
            ]
            writer.writerow(row)
    
    return output.getvalue().encode("utf-8")


@router.get("/wheelset/{ws}/lifecycle/export", tags=["wheelset"])
def wheelset_lifecycle_export(
    ws: int,
    format: str = Query("csv", description="Export format: png, svg, or csv"),
    asof: str | None = Query(None, description="re-anchor at YYYY-MM-DD"),
):
    """Export lifecycle chart data in the requested format.
    
    - format=csv: returns CSV of observations and forecasts
    - format=png: returns matplotlib PNG rendering
    - format=svg: returns matplotlib SVG rendering
    """
    if format not in ("csv", "png", "svg"):
        raise HTTPException(status_code=400, detail=f"unsupported format: {format}. Use csv, png, or svg.")
    
    # Get the trajectory contract
    anchor = pd.Timestamp(asof) if asof else None
    data = service.trajectory(ws, anchor)
    if not data.get("dims"):
        raise HTTPException(status_code=404, detail=f"no data for wheelset {ws}")
    
    contract = dict(data)  # TrajectoryContract dict representation
    
    if format == "csv":
        # Return CSV as streaming response
        csv_bytes = _trajectory_contract_to_csv(contract)
        return StreamingResponse(
            iter([csv_bytes]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=wheelset_{ws}_lifecycle.csv"},
        )
    
    elif format in ("png", "svg"):
        # Use matplotlib render_contract to generate the image
        try:
            # Create temp file that persists beyond this function scope
            # (It will be cleaned up by the OS after response is sent)
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f".{format}",
                prefix=f"wheelset_{ws}_lifecycle_",
                delete=False
            )
            output_dir = Path(temp_file.name).parent
            temp_file.close()
            
            # render_contract saves both PNG and SVG, returns PNG path
            png_path = plot_lifecycle_step.render_contract(contract, output_dir, loco=None)
            
            if format == "png":
                file_path = png_path
            else:  # svg
                file_path = png_path.with_suffix(".svg")
            
            if not file_path.exists():
                raise HTTPException(status_code=500, detail=f"failed to generate {format}")
            
            # Return file as download
            return FileResponse(
                path=file_path,
                media_type="image/png" if format == "png" else "image/svg+xml",
                filename=f"wheelset_{ws}_lifecycle.{format}",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"export error: {str(exc)}") from exc



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
    """Legacy bulk lifecycle PNGs for all wheelsets on a loco.

    Superseded by the per-wheelset trajectory contract and
    `/wheelset/{id}/lifecycle/export`. Gated off by default
    (config.ENABLE_LEGACY_PLOTS); when off, returns 410 with a pointer.
    """
    if not ENABLE_LEGACY_PLOTS:
        raise HTTPException(
            status_code=410,
            detail=("Legacy bulk loco plots are disabled. Use the wheelset "
                    "trajectory contract / /wheelset/{id}/lifecycle/export "
                    "(CSV/PNG/SVG) instead. Set WHEEL_ENABLE_LEGACY_PLOTS=1 to restore."),
        )
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
