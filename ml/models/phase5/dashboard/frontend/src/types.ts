export interface WheelsetHeader {
  wheelset_equipment_id: number;
  loco_number: string | null;
  locomotive_id: number | null;
  latest_measurement: string | null;
  latest_mean_wsmDia: number | null;
  latest_mean_wsmFlange: number | null;
  latest_mean_wsmRoot: number | null;
  latest_mean_wsmThread: number | null;
  days_since_turning: number | null;
  distance_since_turning_km: number | null;
  n_turns: number;
  segment_index: number | null;
  wheel_position_1_12: number | null;
  axle_position_1_6: number | null;
  wheel_profile_2class: number | null;
}

export interface LocomotiveSummary {
  loco_number: string;
  locomotive_id: number | null;
  home_shed: string | null;
  loco_type: string | null;
  n_wheelsets: number;
  n_segments: number;
  n_turns: number;
  wheelsets: WheelsetHeader[];
}

export interface ForecastPoint {
  horizon: number;
  dim: string;
  value: number | null;
  unit: string;
}

export interface TurnProbability {
  horizon: number;
  probability: number | null;
  turn_rate_train: number | null;
  pointer: string;
}

export interface MeasurementPoint {
  measurement_timestamp: string;
  mean_wsmDia: number | null;
  mean_wsmFlange: number | null;
  mean_wsmRoot: number | null;
  mean_wsmThread: number | null;
  mean_wsmFlangeThickness: number | null;
  mean_wsmWheelGauge: number | null;
  segment_index: number | null;
  turn_event: boolean;
  replacement: boolean;
  days_since_turning: number | null;
}

export interface TurnEvent {
  wheelset_equipment_id: number;
  pre_ts: string;
  post_ts: string;
  pre_wsmDia: number | null;
  post_wsmDia: number | null;
  delta_wsmDia: number | null;
  pre_wsmFlange: number | null;
  post_wsmFlange: number | null;
}

export interface WheelsetDetail {
  wheelset_equipment_id: number;
  loco_number: string | null;
  latest_measurement: string | null;
  forecasts: ForecastPoint[];
  turn_probabilities: TurnProbability[];
  turns: TurnEvent[];
  measurements: MeasurementPoint[];
}
