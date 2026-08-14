"""Layer 5 dashboard - typed API schemas."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class WheelsetHeader(BaseModel):
    wheelset_equipment_id: int
    loco_number: str | None = None
    locomotive_id: int | None = None
    latest_measurement: dt.datetime | None = None
    latest_mean_wsmDia: float | None = None
    latest_mean_wsmFlange: float | None = None
    latest_mean_wsmRoot: float | None = None
    latest_mean_wsmThread: float | None = None
    days_since_turning: float | None = None
    distance_since_turning_km: float | None = None
    n_turns: int = 0
    segment_index: int | None = None
    wheel_position_1_12: float | None = None
    axle_position_1_6: float | None = None
    wheel_profile_2class: float | None = None


class SubgroupFlag(BaseModel):
    group: str
    level: str
    reason: str
    n: int
    bias_mm: float | None = None
    coverage: float | None = None
    noise_floor_mm: float | None = None
    note: str = ("Reduced confidence: this wheelset belongs to a subgroup whose "
                 "delta residuals or conformal coverage collapse for this "
                 "dimension/horizon. Interval is shown but the point forecast "
                 "is not decision-grade.")


class ForecastPoint(BaseModel):
    horizon: int
    dim: str
    value: float | None = None
    delta: float | None = None
    current: float | None = None
    low: float | None = None
    high: float | None = None
    implausibility_flag: str | None = None
    model_version: str | None = None
    train_cutoff: str | None = None
    feature_coverage: float | None = None
    subgroup_flags: list[SubgroupFlag] = Field(default_factory=list)
    unit: str = "mm"
    note: str | None = None


class MeasurementPoint(BaseModel):
    measurement_timestamp: dt.datetime
    mean_wsmDia: float | None = None
    mean_wsmFlange: float | None = None
    mean_wsmRoot: float | None = None
    mean_wsmThread: float | None = None
    mean_wsmFlangeThickness: float | None = None
    mean_wsmWheelGauge: float | None = None
    segment_index: int | None = None
    turn_event: bool = False
    replacement: bool = False
    days_since_turning: float | None = None


class TurnEvent(BaseModel):
    wheelset_equipment_id: int
    pre_ts: dt.datetime
    post_ts: dt.datetime
    pre_wsmDia: float | None = None
    post_wsmDia: float | None = None
    delta_wsmDia: float | None = None
    pre_wsmFlange: float | None = None
    post_wsmFlange: float | None = None
    segment_index: int | None = None
    delta_wsmFlangeThickness: float | None = None


class TurnProbability(BaseModel):
    horizon: int
    probability: float | None = None
    turn_rate_train: float | None = None
    n_train: int | None = None
    pointer: str = ("P(turn) = estimated turning probability based on "
                    "historical maintenance behaviour - not a mandatory "
                    "turning recommendation")


class LocomotiveSummary(BaseModel):
    loco_number: str
    locomotive_id: int | None = None
    home_shed: str | None = None
    loco_type: str | None = None
    n_wheelsets: int = 0
    n_segments: int = 0
    n_turns: int = 0
    wheelsets: list[WheelsetHeader] = Field(default_factory=list)


class WheelsetDetail(BaseModel):
    wheelset_equipment_id: int
    loco_number: str | None = None
    latest_measurement: dt.datetime | None = None
    forecasts: list[ForecastPoint] = Field(default_factory=list)
    model: dict | None = None
    feature_coverage: float | None = None
    turn_probabilities: list[TurnProbability] = Field(default_factory=list)
    turns: list[TurnEvent] = Field(default_factory=list)
    measurements: list[MeasurementPoint] = Field(default_factory=list)


class ReplayForecast(BaseModel):
    dim: str
    horizon: int
    current: float | None = None
    predicted: float | None = None
    delta: float | None = None
    actual: float | None = None
    actual_ts: str | None = None
    observed_in_horizon: bool = False
    implausibility_flag: str | None = None
    model_version: str | None = None
    train_cutoff: str | None = None
    feature_coverage: float | None = None
    subgroup_flags: list[SubgroupFlag] = Field(default_factory=list)
    mae: float | None = None


class ReplayPTurn(BaseModel):
    horizon: int
    probability_raw: float
    probability_pct: float
    turn_rate_train: float | None = None
    actual_turned: bool | None = None
    actual_n_events: int | None = None


class WheelsetReplay(BaseModel):
    wheelset_equipment_id: int
    anchor: dt.datetime | None = None
    loco_number: str | None = None
    degradation: list[ReplayForecast] = Field(default_factory=list)
    model: dict | None = None
    turn_probability: list[ReplayPTurn] = Field(default_factory=list)
    time_to_limit_summary: TimeToLimitSummary | None = None
    time_to_limit: dict[str, TimeToLimit] = Field(default_factory=dict)
    note: str | None = None


class FleetBacktest(BaseModel):
    task: str
    contract: str
    split: str
    implausibility_note: str | None = None
    degradation: dict = Field(default_factory=dict)
    turn_probability: dict = Field(default_factory=dict)
    implausibility_diagnostics: dict = Field(default_factory=dict)


class OperationalCaptureCell(BaseModel):
    n_label: int = 0
    turn_rate: float | None = None
    capture: dict[str, float | None] = Field(default_factory=dict)
    note: str | None = None


class OperationalCapture(BaseModel):
    task: str
    source: str
    label: str
    by_dim: dict[str, dict[str, OperationalCaptureCell]] = Field(default_factory=dict)
    note: str | None = None


class TrajectoryObserved(BaseModel):
    ts: dt.datetime
    value: float | None = None
    segment_index: int | None = None
    turn_event: bool = False
    replacement: bool = False


class TrajectoryForecast(BaseModel):
    dim: str
    horizon: int
    asof_ts: dt.datetime | None = None
    current: float | None = None
    delta: float | None = None
    predicted: float | None = None
    low: float | None = None
    high: float | None = None
    model_version: str | None = None
    train_cutoff: str | None = None
    feature_coverage: float | None = None
    subgroup_flags: list[SubgroupFlag] = Field(default_factory=list)


class TrajectoryRealised(BaseModel):
    dim: str
    horizon: int
    ts: dt.datetime | None = None
    actual: float | None = None
    residual: float | None = None
    observed_in_horizon: bool = False


class TimeToLimit(BaseModel):
    dim: str
    limit_mm: float
    direction: str
    label: str
    current_mm: float | None = None
    predicted_at: dict[int, float | None] = Field(default_factory=dict)
    interval_lo: dict[int, float | None] = Field(default_factory=dict)
    interval_hi: dict[int, float | None] = Field(default_factory=dict)
    days_to_limit_point: float | None = None
    days_to_limit_lo: float | None = None
    days_to_limit_hi: float | None = None
    status: str = "beyond_horizon"
    note: str | None = None


class TimeToLimitSummary(BaseModel):
    status: str
    limiting_dim: str | None = None
    limit_mm: float | None = None
    current_mm: float | None = None
    days_to_limit_point: float | None = None
    days_to_limit_lo: float | None = None
    days_to_limit_hi: float | None = None
    note: str | None = None


class TrajectoryDim(BaseModel):
    dim: str
    observed: list[TrajectoryObserved] = Field(default_factory=list)
    forecasts: list[TrajectoryForecast] = Field(default_factory=list)
    realised: list[TrajectoryRealised] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    noise_floor_mm: float | None = None
    time_to_limit: TimeToLimit | None = None


class TrajectoryModelMeta(BaseModel):
    task: str | None = None
    target_mode: str | None = None
    train_cutoff: str | None = None
    n_train: int | None = None
    model_version: str | None = None


class TrajectoryContract(BaseModel):
    wheelset_equipment_id: int
    anchor: dt.datetime | None = None
    asof: dt.datetime | None = None
    contract: str = "trajectory_chart_v1"
    model: TrajectoryModelMeta | None = None
    feature_coverage: float | None = None
    dims: list[TrajectoryDim] = Field(default_factory=list)
    delta_metrics: dict = Field(default_factory=dict)
    time_to_limit_summary: TimeToLimitSummary | None = None
    note: str | None = None


class Capabilities(BaseModel):
    p0_2_dia_fix: bool = False
    degradation_serving: dict = Field(default_factory=dict)
    validation: dict = Field(default_factory=dict)