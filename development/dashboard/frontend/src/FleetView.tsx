import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { FleetOverview, RiskRow } from "./types";
import { EmptyState, ErrorState, SkeletonTable, StaleBanner } from "./States";

function fmt(v: number | null | undefined, d = 2): string {
  return v == null || !isFinite(v) ? "—" : v.toFixed(d);
}

function pct(v: number | null | undefined): string {
  return v == null || !isFinite(v) ? "—" : (v * 100).toFixed(1) + "%";
}

const RISK_LEVELS = ["", "pturn", "condemning", "wear"] as const;
const LIMITING_DIMS = ["", "wsmDia", "wsmFlange", "wsmRoot", "wsmThread"] as const;
/** Hide wheelsets whose latest measurement is older than this (measurement recency, not proven fit). */
const MAX_STALENESS_DAYS = 365;

type SortKey = "pturn_90d" | "pturn_60d" | "pturn_30d" | "days_to_condemning_dia" | "staleness_days" | "mean_wsmFlange" | "mean_wsmRoot" | "mean_wsmThread";

function PturnCell({ v }: { v: number | null | undefined }) {
  return (
    <span className={v != null && v >= 0.01 ? "risk-high" : "risk-low"}>
      {pct(v)}
    </span>
  );
}

export function FleetView({ onSelect }: { onSelect: (ws: number, loco?: string) => void }) {
  const [overview, setOverview] = useState<FleetOverview | null>(null);
  const [rows, setRows] = useState<RiskRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [shed, setShed] = useState("");
  const [locoType, setLocoType] = useState("");
  const [limitingDim, setLimitingDim] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("pturn_90d");
  const [descending, setDescending] = useState(true);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api
      .fleetOverview()
      .then(setOverview)
      .catch((e) => setErr((e as Error).message));
  }, [reload]);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    api
      .fleetRisk({
        shed: shed || undefined,
        loco_type: locoType || undefined,
        limiting_dim: limitingDim || undefined,
        risk_level: riskLevel || undefined,
        sort_by: sortBy,
        descending,
        page,
        page_size: pageSize,
        max_staleness_days: MAX_STALENESS_DAYS,
      })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [shed, locoType, limitingDim, riskLevel, sortBy, descending, page, pageSize, reload]);

  const sheds = useMemo(
    () => (overview?.top_sheds ?? []).map((s) => s.shed_any).filter(Boolean) as string[],
    [overview]
  );

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setDescending(!descending);
    } else {
      setSortBy(key);
      setDescending(true);
    }
  }

  const nPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="fleet">
      {err && !loading && <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />}

      {overview && (
        <section className="fleet-health">
          <StaleBanner days={
            overview.snapshot_built_at
              ? Math.max(0, Math.floor((Date.now() - Date.parse(overview.snapshot_built_at)) / 86400000))
              : null
          } />
          <div className="fleet-health-row">
            <div className="kpi">
              <span className="kpi-label">Fleet wheelsets</span>
              <span className="kpi-value">{overview.n_wheelsets.toLocaleString()}</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Data staleness (median)</span>
              <span className="kpi-value">{fmt(overview.staleness_days_median, 0)} d</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Condemning ≤180 d</span>
              <span className="kpi-value">{overview.days_to_condemning_within_180d.toLocaleString()}</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Snapshot built</span>
              <span className="kpi-value">
                {overview.snapshot_built_at ? overview.snapshot_built_at.slice(0, 10) : "—"}
              </span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Model</span>
              <span className="kpi-value mono">{overview.model_version ?? "—"}</span>
            </div>
          </div>

          <div className="fleet-health-chips">
            {Object.entries(overview.limiting_dim ?? {}).map(([dim, n]) => (
              <span className="chip" key={dim}>
                {dim}: <b>{n.toLocaleString()}</b>
              </span>
            ))}
            <span className="chip-divider">·</span>
            {Object.entries(overview.pturn_share_above_threshold_pct ?? {}).map(([h, pctv]) => (
              <span className="chip" key={h}>
                P(turn) ≥1% @ {h}d: <b>{fmt(pctv, 1)}%</b>
              </span>
            ))}
          </div>
          <p className="muted small">
            Wear distribution (mm) — flange/root/tread q50·q90·q99:{" "}
            {["wsmFlange", "wsmRoot", "wsmThread"].map((d) => {
              const w = overview.wear_distribution_mm?.[d];
              return w ? `${d} ${fmt(w.q50)}/${fmt(w.q90)}/${fmt(w.q99)}` : d;
            }).join("  ·  ")}
          </p>

          {(overview.top_sheds ?? []).length > 0 && (
            <div className="shed-summary">
              <h4>Shed-level summary (top 10 by wheelsets)</h4>
              <div className="table-wrap">
                <table className="risk-table shed-table">
                  <thead>
                    <tr>
                      <th>Shed</th>
                      <th>Wheelsets</th>
                      <th>Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.top_sheds.map((s, i) => (
                      <tr key={i}>
                        <td>
                          <button
                            className="link"
                            onClick={() => { setShed(s.shed_any ?? ""); setPage(1); }}
                          >
                            {s.shed_any ?? "—"}
                          </button>
                        </td>
                        <td>{s.n_wheelsets.toLocaleString()}</td>
                        <td>
                          {overview.n_wheelsets
                            ? ((s.n_wheelsets / overview.n_wheelsets) * 100).toFixed(1) + "%"
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="fleet-risk">
        <div className="fleet-risk-bar">
          <h3>Risk-ranked wheelsets</h3>
          <span className="muted small" title={`wheelsets measured within ${MAX_STALENESS_DAYS}d — measurement recency, not proven fit`}>
            {total.toLocaleString()} wheelsets · measured ≤{MAX_STALENESS_DAYS}d
          </span>
          <select value={shed} onChange={(e) => { setShed(e.target.value); setPage(1); }}>
            <option value="">Shed: all</option>
            {sheds.slice(0, 40).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select value={locoType} onChange={(e) => { setLocoType(e.target.value); setPage(1); }}>
            <option value="">Loco type: all</option>
            {Array.from(new Set(rows.map((r) => r.loco_type).filter(Boolean))).map((t) => (
              <option key={t} value={t ?? ""}>{t}</option>
            ))}
          </select>
          <select value={limitingDim} onChange={(e) => { setLimitingDim(e.target.value); setPage(1); }}>
            {LIMITING_DIMS.map((d) => (
              <option key={d} value={d}>{d ? `Limiting: ${d}` : "Limiting: all"}</option>
            ))}
          </select>
          <select value={riskLevel} onChange={(e) => { setRiskLevel(e.target.value); setPage(1); }}>
            {RISK_LEVELS.map((l) => (
              <option key={l} value={l}>{l ? `Risk: ${l}` : "Risk: all"}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <SkeletonTable rows={8} cols={12} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No wheelsets match the current filters"
            hint="Try clearing the shed / type / risk filters above."
          />
        ) : (
          <div className="table-wrap">
            <table className="risk-table">
              <thead>
                <tr>
                  <th onClick={() => toggleSort("pturn_90d")} className="sortable">
                    P(turn) 90d {sortBy === "pturn_90d" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th className={sortBy === "pturn_60d" ? "sorted" : ""}>
                    P(turn) 60d
                  </th>
                  <th className={sortBy === "pturn_30d" ? "sorted" : ""}>
                    P(turn) 30d
                  </th>
                  <th>Loco</th>
                  <th>Wheelset</th>
                  <th>Shed</th>
                  <th onClick={() => toggleSort("mean_wsmFlange")} className="sortable">
                    Flange {sortBy === "mean_wsmFlange" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("mean_wsmRoot")} className="sortable">
                    Root {sortBy === "mean_wsmRoot" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("mean_wsmThread")} className="sortable">
                    Thread {sortBy === "mean_wsmThread" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th>Limiting</th>
                  <th onClick={() => toggleSort("days_to_condemning_dia")} className="sortable">
                    Condemning {sortBy === "days_to_condemning_dia" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("staleness_days")} className="sortable">
                    Staleness {sortBy === "staleness_days" ? (descending ? "↓" : "↑") : ""}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.wheelset_equipment_id}
                    className="clickable"
                    onClick={() => onSelect(r.wheelset_equipment_id, r.loco_number ?? undefined)}
                  >
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_90d} />
                    </td>
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_60d} />
                    </td>
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_30d} />
                    </td>
                    <td>{r.loco_number ?? "—"}</td>
                    <td className="mono">#{r.wheelset_equipment_id}</td>
                    <td>{r.shed_any ?? "—"}</td>
                    <td>{fmt(r.mean_wsmFlange)}</td>
                    <td>{fmt(r.mean_wsmRoot)}</td>
                    <td>{fmt(r.mean_wsmThread)}</td>
                    <td>{r.limiting_dim ?? "—"}</td>
                    <td>{fmt(r.days_to_condemning_dia, 0)} d</td>
                    <td>{fmt(r.staleness_days, 0)} d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > 0 && (
          <div className="pager">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <span className="muted small">page {page} / {nPages}</span>
            <button disabled={page >= nPages} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        )}
      </section>
    </div>
  );
}
