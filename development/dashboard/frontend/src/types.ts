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

export interface SubgroupFlag {
  group: string;
  level: string;
  reason: "bias" | "coverage" | string;
  n: number;
  bias_mm: number | null;
  coverage: number | null;
  noise_floor_mm: number | null;
  note: string;
}

export interface ForecastPoint {
  horizon: number;
  dim: string;
  value: number | null;
  delta: number | null;
  current: number | null;
  low: number | null;
  high: number | null;
  implausibility_flag: string | null;
  model_version: string | null;
  train_cutoff: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
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
  model: ModelMeta | null;
  feature_coverage: number | null;
  turn_probabilities: TurnProbability[];
  turns: TurnEvent[];
  measurements: MeasurementPoint[];
}

export interface ModelMeta {
  task?: string | null;
  target_mode?: string | null;
  train_cutoff?: string | null;
  n_train?: number | null;
  model_version?: string | null;
}

export interface ReplayForecast {
  dim: string;
  horizon: number;
  current: number | null;
  predicted: number | null;
  actual: number | null;
  actual_ts: string | null;
  observed_in_horizon: boolean;
  implausibility_flag: string | null;
  model_version: string | null;
  train_cutoff: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
  mae: number | null;
}

export interface ReplayPTurn {
  horizon: number;
  probability_raw: number;
  probability_pct: number;
  turn_rate_train: number | null;
  actual_turned: boolean | null;
  actual_n_events: number | null;
}

export interface WheelsetReplay {
  wheelset_equipment_id: number;
  anchor: string | null;
  loco_number: string | null;
  degradation: ReplayForecast[];
  model: ModelMeta | null;
  turn_probability: ReplayPTurn[];
  time_to_limit_summary: TimeToLimitSummary | null;
  time_to_limit: Record<string, TimeToLimit>;
  note: string | null;
}

export interface FleetBacktest {
  task: string;
  contract: string;
  split: string;
  implausibility_note: string | null;
  degradation: FleetDegradation;
  turn_probability: {
    horizons?: Record<string, { models?: Record<string, BacktestModel> }>;
    [k: string]: unknown;
  };
  implausibility_diagnostics: Record<
    string,
    Record<string, { n: number; flag: string; actual_rate: number; model_rate: number }>
  >;
}

export interface OperationalCaptureCell {
  n_label: number;
  turn_rate: number | null;
  capture: Record<string, number | null>;
  note?: string | null;
}

export interface OperationalCapture {
  task: string;
  source: string;
  label: string;
  by_dim: Record<string, Record<string, OperationalCaptureCell>>;
  note: string | null;
}

export interface TrajectoryObserved {
  ts: string;
  value: number | null;
  segment_index: number | null;
  turn_event: boolean;
  replacement: boolean;
}

export interface TrajectoryForecast {
  dim: string;
  horizon: number;
  asof_ts: string | null;
  current: number | null;
  delta: number | null;
  predicted: number | null;
  low: number | null;
  high: number | null;
  model_version: string | null;
  train_cutoff: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
}

export interface TrajectoryRealised {
  dim: string;
  horizon: number;
  ts: string | null;
  actual: number | null;
  residual: number | null;
  observed_in_horizon: boolean;
}

export interface TimeToLimit {
  dim: string;
  limit_mm: number;
  direction: "down" | "up" | string;
  label: string;
  current_mm: number | null;
  predicted_at: Record<number, number | null>;
  interval_lo: Record<number, number | null>;
  interval_hi: Record<number, number | null>;
  days_to_limit_point: number | null;
  days_to_limit_lo: number | null;
  days_to_limit_hi: number | null;
  status: "within_horizon" | "beyond_horizon" | "at_limit" | string;
  note: string | null;
}

export interface TimeToLimitSummary {
  status: string;
  limiting_dim: string | null;
  limit_mm: number | null;
  current_mm: number | null;
  days_to_limit_point: number | null;
  days_to_limit_lo: number | null;
  days_to_limit_hi: number | null;
  note: string | null;
}

export interface TrajectoryDim {
  dim: string;
  observed: TrajectoryObserved[];
  forecasts: TrajectoryForecast[];
  realised: TrajectoryRealised[];
  flags: string[];
  noise_floor_mm: number | null;
  time_to_limit: TimeToLimit | null;
}

export interface TrajectoryModelMeta {
  task: string | null;
  target_mode: string | null;
  train_cutoff: string | null;
  n_train: number | null;
  model_version: string | null;
}

export interface TurnMarker {
  turn_no: number;
  pre_ts: string | null;
  post_ts: string;
  segment_index: number | null;
  days_between: number | null;
  pre_wsmDia: number | null;
  post_wsmDia: number | null;
  dia_cut: number | null;
  pre_wsmFlange: number | null;
  post_wsmFlange: number | null;
  pre_wsmRoot: number | null;
  post_wsmRoot: number | null;
  pre_wsmThread: number | null;
  post_wsmThread: number | null;
}

export interface TrajectoryContract {
  wheelset_equipment_id: number;
  loco_number: string | null;
  anchor: string | null;
  asof: string | null;
  contract: string;
  units: Record<string, string>;
  model: TrajectoryModelMeta | null;
  feature_coverage: number | null;
  dims: TrajectoryDim[];
  turns: TurnMarker[];
  delta_metrics: Record<string, Record<string, { mae_mm?: number; delta_r2?: number; delta_spearman?: number }>>;
  time_to_limit_summary: TimeToLimitSummary | null;
  note: string | null;
}

export interface Capabilities {
  p0_2_dia_fix: boolean;
  degradation_serving: {
    model_version?: string | null;
    train_cutoff?: string | null;
    n_train?: number | null;
    target_mode?: string | null;
  };
  validation?: {
    warnings?: string[];
  };
}

export interface FleetOverview {
  n_wheelsets: number;
  snapshot_built_at: string | null;
  model_version: string | null;
  train_cutoff: string | null;
  staleness_days_median: number | null;
  limiting_dim: Record<string, number>;
  pturn_share_above_threshold_pct: Record<string, number>;
  wear_distribution_mm: Record<string, Record<string, number | null>>;
  days_to_condemning_within_180d: number;
  feature_days_since_turning: Record<string, number | null>;
  top_sheds: Array<{ shed_any?: string | null; n_wheelsets: number }>;
}

export interface RiskRow {
  wheelset_equipment_id: number;
  loco_number: string | null;
  shed_any: string | null;
  loco_type: string | null;
  limiting_dim: string | null;
  limiting_reason: string | null;
  days_to_condemning_dia: number | null;
  mean_wsmDia: number | null;
  mean_wsmFlange: number | null;
  mean_wsmRoot: number | null;
  mean_wsmThread: number | null;
  pturn_30d: number | null;
  pturn_60d: number | null;
  pturn_90d: number | null;
  feature_coverage: number | null;
  staleness_days: number | null;
  latest_measurement: string | null;
}

export interface FleetRiskResponse {
  total: number;
  page: number;
  page_size: number;
  items: RiskRow[];
  columns: string[];
}

export interface SearchHit {
  loco_number: string | null;
  shed: string | null;
  loco_type: string | null;
  n_wheelsets: number;
}

export interface FleetSearchResponse {
  query: string;
  total: number;
  items: SearchHit[];
}

export interface ShedOverview {
  shed: string;
  n_wheelsets: number;
  n_locos: number;
  limiting_dim: Record<string, number>;
  pturn_90d_mean_pct: number | null;
  pturn_90d_p90_pct: number | null;
  days_to_condemning_within_180d: number;
  staleness_days_median: number | null;
  error?: string | null;
}

export interface BacktestModel {
  n_test: number;
  turn_rate_test: number;
  turn_rate_pred: number;
  roc_auc: number | null;
  pr_auc: number | null;
  brier: number;
  ece: number;
  capture?: Record<string, { k: number; turns_captured: number; share_of_turns: number; precision: number }>;
}

export interface DegradationCell {
  n_train?: number;
  n_test?: number;
  models?: Record<
    string,
    {
      mae?: number;
      r2?: number;
      spearman?: number;
      delta_mae?: number;
      delta_r2?: number;
      delta_spearman?: number;
      [k: string]: unknown;
    }
  >;
}

export interface FleetDegradation {
  static?: Record<string, Record<string, DegradationCell>>;
  rolling?: unknown;
  [k: string]: unknown;
}
