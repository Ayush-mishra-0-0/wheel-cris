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


class ForecastPoint(BaseModel):
    horizon: int
    dim: str
    value: float | None = None
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
    turn_probabilities: list[TurnProbability] = Field(default_factory=list)
    turns: list[TurnEvent] = Field(default_factory=list)
    measurements: list[MeasurementPoint] = Field(default_factory=list)


class ReplayForecast(BaseModel):
    dim: str
    horizon: int
    current: float | None = None
    predicted: float | None = None
    actual: float | None = None
    actual_ts: str | None = None
    observed_in_horizon: bool = False
    implausibility_flag: str | None = None
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
    turn_probability: list[ReplayPTurn] = Field(default_factory=list)
    note: str | None = None


class FleetBacktest(BaseModel):
    task: str
    contract: str
    split: str
    implausibility_note: str | None = None
    degradation: dict = Field(default_factory=dict)
    turn_probability: dict = Field(default_factory=dict)
    implausibility_diagnostics: dict = Field(default_factory=dict)