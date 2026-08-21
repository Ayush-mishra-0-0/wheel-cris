import type {
  Capabilities,
  DispositionRecord,
  FleetBacktest,
  FleetLocos,
  FleetOverview,
  FleetRiskResponse,
  FleetSearchResponse,
  FleetTrend,
  FleetWorklistResponse,
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

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
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
  fleetTrend: () => get<FleetTrend>(`/fleet/trend`),
  fleetWorklist: (k = 10, shed?: string) =>
    get<FleetWorklistResponse>(`/fleet/worklist`, { k, shed: shed ?? null }),
  dispositions: (id: number) => get<DispositionRecord[]>(`/wheelset/${id}/dispositions`),
  recordDisposition: (id: number, action: string, note?: string, loco?: string | null) =>
    post<DispositionRecord>(`/wheelset/${id}/disposition`, { action, note, loco_number: loco ?? null }),
  fleetLocos: () => get<FleetLocos>(`/fleet/locos`),
  modelHealth: () => get<ModelHealth>(`/model/health`),
  shed: (shed: string) => get<ShedOverview>(`/shed/${encodeURIComponent(shed)}`),
  config: () => get<Capabilities>(`/config`),
};
