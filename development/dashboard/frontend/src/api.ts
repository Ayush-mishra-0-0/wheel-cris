import type {
  FleetBacktest,
  LocomotiveSummary,
  OperationalCapture,
  TrajectoryContract,
  WheelsetDetail,
  WheelsetReplay,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  loco: (num: string) => get<LocomotiveSummary>(`/loco/${encodeURIComponent(num)}`),
  wheelsetOverview: (id: number) =>
    get<WheelsetDetail>(`/wheelset/${id}/overview`),
  wheelsetBacktest: (id: number, asof: string) =>
    get<WheelsetReplay>(`/wheelset/${id}/backtest?asof=${encodeURIComponent(asof)}`),
  trajectory: (id: number, asof?: string) =>
    get<TrajectoryContract>(
      asof
        ? `/wheelset/${id}/trajectory?asof=${encodeURIComponent(asof)}`
        : `/wheelset/${id}/trajectory`
    ),
  fleetBacktest: () => get<FleetBacktest>(`/backtest/fleet`),
  fleetCapture: () => get<OperationalCapture>(`/backtest/fleet/capture`),
  locoPlots: (loco: string) =>
    get<{ loco: string; images: Record<string, string>; svgs: Record<string, string> }>(
      `/loco/${encodeURIComponent(loco)}/plots`
    ),
};
