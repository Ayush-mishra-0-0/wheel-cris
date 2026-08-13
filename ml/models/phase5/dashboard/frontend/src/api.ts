import type { LocomotiveSummary, WheelsetDetail } from "./types";

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
};
