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
  staleness_days?: number;
  latest_loco_agrees?: boolean;
  is_recently_measured?: boolean;
  /** Backward-compatible alias for is_recently_measured (measurement recency, not proven fit). */
  is_current_fit?: boolean;
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

export interface LocoWheelsetRow extends WheelsetHeader {
  limiting_dim: string | null;
  limiting_reason: string | null;
  days_to_condemning_dia: number | null;
  pturn_30d: number | null;
  pturn_60d: number | null;
  pturn_90d: number | null;
  pturn_30d_calibrated: number | null;
  pturn_60d_calibrated: number | null;
  pturn_90d_calibrated: number | null;
  pturn_30d_decile: number | null;
  pturn_60d_decile: number | null;
  pturn_90d_decile: number | null;
  fc_wsmRoot_90d: number | null;
  fc_wsmFlange_90d: number | null;
  fc_wsmThread_90d: number | null;
  wear_bands?: Record<string, WearBand>;
}

export interface LocoWheelsetTable {
  loco_number: string;
  locomotive_id: number | null;
  home_shed: string | null;
  loco_type: string | null;
  n_wheelsets: number;
  n_wheelsets_current?: number;
  n_wheelsets_historical?: number;
  n_expected_axles?: number | null;
  recency_threshold_days?: number;
  n_segments: number;
  n_turns: number;
  snapshot_sourced: boolean;
  wheelsets: LocoWheelsetRow[];
  wheelsets_all?: LocoWheelsetRow[];
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
  model_of_record?: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
  unit: string;
}

export interface TurnProbability {
  horizon: number;
  probability: number | null;
  calibrated_probability?: number | null;
  conf_decile?: number | null;
  calibration_source?: string | null;
  turn_rate_train: number | null;
  pointer: string;
  roc_auc?: number | null;
  turn_rate_test?: number | null;
}

export interface Contributor {
  feature: string;
  label: string;
  shap: number;
}

export interface WheelAttribution {
  target: string;
  wheelset_equipment_id: number;
  measurement_record_id?: number | null;
  locomotive_id?: number | null;
  anchor?: string | null;
  probability?: number | null;
  risk?: string | null;
  conf_decile?: number | null;
  conf_empirical_rate?: number | null;
  train_prevalence?: number | null;
  realized_event?: boolean | null;
  contributors: Contributor[];
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
  dia_cut?: number | null;
  reason_of_turning?: string | null;
  reason_of_turning_raw_code?: number | null;
  reason_of_turning_source?: string | null;
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
  model_of_record?: Record<string, string> | null;
}

export interface WheelAdaptation {
  prior_n: number;
  bias_mm: number | null;
  applied: boolean;
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
  model_of_record?: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
  wheel_adaptation: WheelAdaptation;
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
  turn_reset: TurnReset;
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
  model_of_record?: string | null;
  feature_coverage: number | null;
  subgroup_flags: SubgroupFlag[];
  wheel_adaptation: WheelAdaptation;
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

export interface ConformalCell {
  level: number;
  width_mm: number | null;
  coverage: number | null;
}

export interface TrajectoryModelMeta {
  task: string | null;
  target_mode: string | null;
  train_cutoff: string | null;
  n_train: number | null;
  model_version: string | null;
  model_of_record?: Record<string, string> | null;
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
  reason_of_turning?: string | null;
  reason_of_turning_raw_code?: number | null;
  reason_of_turning_source?: string | null;
  pre_wsmFlange: number | null;
  post_wsmFlange: number | null;
  pre_wsmRoot: number | null;
  post_wsmRoot: number | null;
  pre_wsmThread: number | null;
  post_wsmThread: number | null;
}

export interface SegmentBand {
  segment_index: number | null;
  start_ts: string | null;
  end_ts: string | null;
  n_measurements: number;
  boundary_kind: string | null;
}

export interface LimitingDimProvenance {
  limiting_dim_verified: string | null;
  limiting_dim_source: string | null;
  limiting_dim_heuristic: string | null;
  limiting_reason: string | null;
  prior: number | null;
  contract: string | null;
}

export interface TurnReset {
  condition: string;
  boundary_kind: string | null;
  cut_dia_mm: number | null;
  restore: Record<string, number | null>;
  restore_claimed: boolean;
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
  turn_reset: TurnReset;
  segments: SegmentBand[];
  limiting_dim_provenance: LimitingDimProvenance | null;
  delta_metrics: Record<string, Record<string, { mae_mm?: number; delta_r2?: number; delta_spearman?: number }>>;
  conformal: Record<string, Record<string, ConformalCell>>;
  forecast_condition: string | null;
  monotone_enforced: boolean;
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
    model_of_record?: Record<string, string> | null;
  };
  action_ladder?: {
    status?: string | null;
    ready?: boolean;
    tiers?: Array<{ tier: string; label?: string | null; basis?: string | null; thresholds_present?: boolean }>;
  };
  limits?: Record<
    string,
    {
      limit_mm: number | null;
      direction: string;
      label: string;
      unit: string;
      status: "approved" | "provisional" | "pending" | string;
      owner: string;
      note: string;
    }
  >;
  validation?: {
    warnings?: string[];
  };
  data_health?: DataHealth;
}

export interface DataHealthItem {
  name: string;
  built_at: string | null;
  note: string;
  rows?: number;
  path?: string;
  missing?: boolean;
}

export interface DataHealth {
  scope_status?: string | null;
  wes_version?: string | null;
  items: DataHealthItem[];
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
  model_of_record_ranking?: {
    primary?: string | null;
    primary_label?: string | null;
    roots?: string[];
    secondary?: string | null;
    note?: string | null;
  };
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
  pturn_30d_calibrated: number | null;
  pturn_60d_calibrated: number | null;
  pturn_90d_calibrated: number | null;
  pturn_30d_decile: number | null;
  pturn_60d_decile: number | null;
  pturn_90d_decile: number | null;
  wear_bands?: Record<string, WearBand>;
  feature_coverage: number | null;
  staleness_days: number | null;
  latest_measurement: string | null;
}

export interface WearBand {
  band: "healthy" | "watch" | "near" | "unknown" | string;
  headroom: number | null;
  limit_mm: number | null;
}

export interface FleetRiskResponse {
  total: number;
  page: number;
  page_size: number;
  ranked_by?: string | null;
  max_staleness_days: number | null;
  days_to_condemning_max?: number | null;
  pturn_min?: number | null;
  items: RiskRow[];
  columns: string[];
}

export interface FleetTrendPoint {
  date: string;
  n_wheelsets: number;
  pturn_90d_cal_ge1pct_pct: number | null;
  pturn_90d_cal_ge5pct_pct: number | null;
  limiting_dim: Record<string, number>;
  condemning_within_180d: number | null;
  staleness_days_median: number | null;
  source: string;
}

export interface FleetTrend {
  points: FleetTrendPoint[];
  note?: string | null;
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

export interface FleetWorklistItem {
  shed_any: string;
  loco_number: string | null;
  loco_type: string | null;
  wheelset_equipment_id: number;
  axle_position_1_6: number | null;
  wheel_position_1_12: number | null;
  limiting_dim: string | null;
  limiting_reason: string | null;
  days_to_condemning_dia: number | null;
  mean_wsmDia: number | null;
  mean_wsmFlange: number | null;
  mean_wsmRoot: number | null;
  mean_wsmThread: number | null;
  staleness_days: number | null;
  latest_measurement: string | null;
  rank_score: number | null;
  rank_score_kind: string | null;
  pturn_90d_decile: number | null;
  wear_bands?: Record<string, WearBand>;
}

export interface FleetWorklistResponse {
  k_per_shed: number;
  n_sheds: number;
  total: number;
  generated_at: string | null;
  items: FleetWorklistItem[];
}

export interface DispositionRecord {
  ts_utc: string | null;
  wheelset_equipment_id: number;
  loco_number: string | null;
  action: string;
  note: string | null;
  context?: {
    snapshot_built_at?: string | null;
    pturn_90d_calibrated?: number | null;
    pturn_90d_decile?: number | null;
  };
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

export interface ConformalHealth {
  level: number;
  width_mm: number | null;
  coverage: number | null;
  n_fit: number | null;
  n_cal: number | null;
  n_test: number | null;
}

export interface DegradationHealthCell {
  mae_mm: number | null;
  r2: number | null;
  spearman: number | null;
  noise_floor_mm: number | null;
  conformal: ConformalHealth;
  capture_at_1_pct: number | null;
  capture_at_5_pct: number | null;
  capture_at_10_pct: number | null;
}

export interface PturnHealthCell {
  roc_auc: number | null;
  pr_auc: number | null;
  brier: number | null;
  ece: number | null;
  n_test: number | null;
  turn_rate_train: number | null;
  turn_rate_test: number | null;
  calibration?: { bin_rates?: Array<number | null>; train_prevalence?: number | null } | null;
}

export interface ModelHealth {
  degradation: Record<string, Record<string, DegradationHealthCell>>;
  pturn: Record<string, PturnHealthCell>;
  provenance: {
    trajectory_artefact_contract?: string | null;
    trajectory_artefact_task?: string | null;
    turn_probability_contract?: string | null;
    artefact_generated?: string | null;
    predicted?: boolean;
    note?: string | null;
  };
}

export interface LocoSwitcherItem {
  loco_number: string;
  n_wheelsets: number;
  n_recent: number;
  locos_note?: string | null;
}

export interface FleetLocos {
  total: number;
  locos: LocoSwitcherItem[];
  error?: string | null;
  note?: string | null;
}
