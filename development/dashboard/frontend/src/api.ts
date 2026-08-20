import type {
  Capabilities,
  FleetBacktest,
  FleetLocos,
  FleetOverview,
  FleetRiskResponse,
  FleetSearchResponse,
  LocomotiveSummary,
  LocoWheelsetTable,
  ModelHealth,
  OperationalCapture,
  ShedOverview,
  TrajectoryContract,
  WheelAttribution,
  WheelsetDetail,
  WheelsetReplay,
} from "./types";

const BASE = "/api/v1";

async function get<T>(path: string, params?: Record<string, string | number | boolean | null>): Promise<T> {
  const qs = params
    ? "?" + new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v !== undefined && v !== null && v !== "")
          .map(([k, v]) => [k, String(v)])
      ).toString()
    : "";
  const res = await fetch(`${BASE}${path}${qs}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  loco: (num: string) => get<LocomotiveSummary>(`/loco/${encodeURIComponent(num)}`),
  locoWheelsets: (num: string) =>
    get<LocoWheelsetTable>(`/loco/${encodeURIComponent(num)}/wheelsets`),
  wheelsetOverview: (id: number) =>
    get<WheelsetDetail>(`/wheelset/${id}/overview`),
  wheelsetAttribution: (id: number, target: "turn" | "root" = "turn") =>
    get<WheelAttribution>(`/wheelset/${id}/attribution`, { target }),
  wheelsetBacktest: (id: number, asof: string) =>
    get<WheelsetReplay>(`/wheelset/${id}/backtest`, { asof }),
  trajectory: (id: number, asof?: string) =>
    get<TrajectoryContract>(`/wheelset/${id}/lifecycle`, asof ? { asof } : undefined),
  fleetBacktest: () => get<FleetBacktest>(`/backtest/fleet`),
  fleetCapture: () => get<OperationalCapture>(`/backtest/fleet/capture`),
  fleetOverview: () => get<FleetOverview>(`/fleet/overview`),
  fleetRisk: (params?: {
    shed?: string;
    loco_type?: string;
    limiting_dim?: string;
    risk_level?: string;
    sort_by?: string;
    descending?: boolean;
    page?: number;
    page_size?: number;
    max_staleness_days?: number | null;
    days_to_condemning_max?: number | null;
    pturn_min?: number | null;
  }) => get<FleetRiskResponse>(`/fleet/risk`, params),
  fleetSearch: (q: string) => get<FleetSearchResponse>(`/fleet/search`, { q }),
  fleetLocos: () => get<FleetLocos>(`/fleet/locos`),
  modelHealth: () => get<ModelHealth>(`/model/health`),
  shed: (shed: string) => get<ShedOverview>(`/shed/${encodeURIComponent(shed)}`),
  config: () => get<Capabilities>(`/config`),
};
