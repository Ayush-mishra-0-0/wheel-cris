import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { api } from "./api";
import type { Capabilities, FleetOverview, FleetTrend, RiskRow } from "./types";
import { LimitChip, WearBands } from "./LimitChip";
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

const PRESETS: { key: string; label: string; sort_by: SortKey; desc: boolean; note: string }[] = [
  { key: "pturn", label: "P(turn)", sort_by: "pturn_90d", desc: true, note: "primary ranking = calibrated 90d P(turn) (Phase 4 Target B realized rate) — maintenance behaviour, not an engineering limit" },
  { key: "wear", label: "Wear (flange)", sort_by: "mean_wsmFlange", desc: true, note: "current wear level — closest to an engineering signal" },
  { key: "condemning", label: "Condemning (dia)", sort_by: "days_to_condemning_dia", desc: false, note: "days to the 1016 mm dia hard stop — ascending = most urgent" },
  { key: "staleness", label: "Recency", sort_by: "staleness_days", desc: false, note: "oldest measurements first — data quality, not risk" },
];

type QueueKey = "all" | "due_30d" | "pturn_wear" | "reduced";
const QUEUES: { key: QueueKey; label: string; note: string; disabled?: boolean }[] = [
  { key: "all", label: "All wheelsets", note: "no action-queue filter" },
  { key: "due_30d", label: "Due ≤30 d (condemning)", note: "wheelsets ≤30 d from the approved 1016 mm dia hard stop, soonest first" },
  { key: "pturn_wear", label: "P(turn) ≥5% + wear", note: "high wear-limit wheelsets with 90 d P(turn) ≥5% — combined signal" },
  { key: "reduced", label: "Reduced-confidence only", note: "needs subgroup flags in the fleet snapshot (rebuild) — not yet available", disabled: true },
];

function PturnCell({ v, raw, decile }: { v: number | null | undefined; raw?: number | null | undefined; decile?: number | null | undefined }) {
  const tip =
    raw != null
      ? `raw model score ${(raw * 100).toFixed(2)}% · calibrated = realized rate of the score's decile${decile != null ? ` (decile ${decile}/9)` : ""}`
      : undefined;
  return (
    <span className={v != null && v >= 0.01 ? "risk-high" : "risk-low"} title={tip}>
      {pct(v)}
    </span>
  );
}

export function FleetView({ onSelect, caps }: { onSelect: (ws: number, loco?: string) => void; caps?: Capabilities | null }) {
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
  const [preset, setPreset] = useState("pturn");
  const [focusedIdx, setFocusedIdx] = useState(0);
  const [wlBusy, setWlBusy] = useState(false);
  const [wlErr, setWlErr] = useState<string | null>(null);
  const [trend, setTrend] = useState<FleetTrend | null>(null);
  const tbodyRef = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    api.fleetTrend().then(setTrend).catch(() => setTrend(null));
  }, [reload]);

  // action-queue state (shareable via URL ?shed=&queue=&preset=)
  const [queue, setQueue] = useState<QueueKey>(() => {
    const q = new URLSearchParams(window.location.search).get("queue");
    return q === "due_30d" || q === "pturn_wear" ? q : "all";
  });
  const [daysToCondMax, setDaysToCondMax] = useState<number | null>(() =>
    new URLSearchParams(window.location.search).get("queue") === "due_30d" ? 30 : null
  );
  const [pturnMin, setPturnMin] = useState<number | null>(() =>
    new URLSearchParams(window.location.search).get("queue") === "pturn_wear" ? 0.05 : null
  );

  // keep URL shareable: ?shed=&queue=&preset=&sort_by=&descending=
  useEffect(() => {
    const p = new URLSearchParams();
    if (shed) p.set("shed", shed);
    if (queue && queue !== "all") p.set("queue", queue);
    if (preset && preset !== "pturn") p.set("preset", preset);
    if (sortBy !== "pturn_90d") p.set("sort_by", sortBy);
    if (!descending) p.set("descending", "false");
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [shed, queue, preset, sortBy, descending]);

  // shareable initial filter/sort from URL (?shed=&queue=&preset=&sort_by=&descending=)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const shed = p.get("shed");
    const sort = p.get("sort_by") as SortKey | null;
    const preset = p.get("preset");
    const descRaw = p.get("descending");
    if (shed) setShed(shed);
    if (preset && PRESETS.some((x) => x.key === preset)) setPreset(preset);
    if (sort && PRESETS.concat([]).some((x) => x.sort_by === sort)) {
      setSortBy(sort);
      setDescending(descRaw !== "false");
    }
  }, []);

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
        days_to_condemning_max: daysToCondMax,
        pturn_min: pturnMin,
      })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
        setFocusedIdx(0);
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [shed, locoType, limitingDim, riskLevel, sortBy, descending, page, pageSize, reload, daysToCondMax, pturnMin]);

  const sheds = useMemo(
    () => (overview?.top_sheds ?? []).map((s) => s.shed_any).filter(Boolean) as string[],
    [overview]
  );

  function toggleSort(key: SortKey) {
    setPreset("");
    if (sortBy === key) {
      setDescending(!descending);
    } else {
      setSortBy(key);
      setDescending(true);
    }
  }

  function applyPreset(key: string) {
    const p = PRESETS.find((x) => x.key === key);
    if (!p) return;
    setPreset(key);
    setSortBy(p.sort_by);
    setDescending(p.desc);
  }

  function applyQueue(key: QueueKey) {
    setQueue(key);
    setPage(1);
    if (key === "due_30d") {
      setDaysToCondMax(30);
      setPturnMin(null);
      setRiskLevel("");
      setSortBy("days_to_condemning_dia");
      setDescending(false);
    } else if (key === "pturn_wear") {
      setDaysToCondMax(null);
      setPturnMin(0.05);
      setRiskLevel("wear");
      setSortBy("pturn_90d");
      setDescending(true);
    } else {
      setDaysToCondMax(null);
      setPturnMin(null);
    }
  }

  // selecting a raw filter manually exits the action-queue preset
  function clearQueue() {
    setQueue("all");
  }

  const activeQueue = QUEUES.find((x) => x.key === queue);

  const nPages = Math.max(1, Math.ceil(total / pageSize));

  function focusRow(i: number) {
    const tr = tbodyRef.current?.querySelector<HTMLTableRowElement>(`tr[data-i='${i}']`);
    tr?.focus();
  }

  function moveFocus(d: number) {
    const next = Math.max(0, Math.min(rows.length - 1, focusedIdx + d));
    setFocusedIdx(next);
    focusRow(next);
  }

  function onRowKey(e: KeyboardEvent<HTMLTableRowElement>, i: number) {
    if (e.key === "ArrowDown") { e.preventDefault(); moveFocus(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveFocus(-1); }
    else if (e.key === "Enter" && rows[i]) {
      e.preventDefault();
      onSelect(rows[i].wheelset_equipment_id, rows[i].loco_number ?? undefined);
    }
  }

  function exportCsv() {
    const header = ["wheelset_equipment_id", "loco_number", "shed_any", "limiting_dim",
      "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot", "mean_wsmThread",
      "pturn_30d", "pturn_60d", "pturn_90d", "days_to_condemning_dia", "staleness_days", "latest_measurement"];
    const lines = [header.join(",")];
    for (const r of rows) {
      lines.push(header.map((h) => {
        const v = (r as unknown as Record<string, unknown>)[h];
        if (v == null) return "";
        const s = String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fleet_risk_${queue !== "all" ? queue + "_" : ""}${preset || "sorted"}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  async function exportWorklist() {
    setWlErr(null);
    try {
      const wl = await api.fleetWorklist(10, shed || undefined);
      const header = ["shed_any", "loco_number", "wheelset_equipment_id",
        "axle_position_1_6", "wheel_position_1_12", "rank_score", "rank_score_kind",
        "pturn_90d_decile", "limiting_dim", "limiting_reason",
        "days_to_condemning_dia", "mean_wsmDia", "mean_wsmFlange", "mean_wsmRoot",
        "mean_wsmThread", "staleness_days", "latest_measurement"];
      const lines = [header.join(","),
        `# top-${wl.k_per_shed} per shed by calibrated 90d P(turn); ${wl.n_sheds} sheds; ${wl.total} rows; generated ${wl.generated_at}`];
      for (const r of wl.items) {
        lines.push(header.map((h) => {
          const v = (r as unknown as Record<string, unknown>)[h];
          if (v == null) return "";
          const s = String(v);
          return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        }).join(","));
      }
      const blob = new Blob([lines.join("\n")], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `worklist_top10_per_shed${shed ? "_" + shed : ""}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setWlErr((e as Error).message);
    }
  }


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
          {trend && trend.points.length >= 2 && (
            <div className="trend-strip">
              <span className="muted small">Snapshot trend:</span>
              {trend.points.map((p) => (
                <span
                  key={p.date}
                  className="chip"
                  title={`${p.n_wheelsets.toLocaleString()} wheelsets · condemning ≤180d: ${p.condemning_within_180d ?? "—"} · median staleness ${fmt(p.staleness_days_median, 0)} d`}
                >
                  {p.date}: <b>{fmt(p.pturn_90d_cal_ge1pct_pct, 1)}%</b> ≥1% cal P(turn)
                </span>
              ))}
            </div>
          )}
          {trend && trend.points.length === 1 && (
            <p className="muted small">
              Snapshot history collecting — a dated archive is written on every rebuild; the
              trend strip appears from the second point.
            </p>
          )}
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
                            onClick={() => { setShed(s.shed_any ?? ""); setPage(1); clearQueue(); }}
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
          <select
            value={queue}
            onChange={(e) => applyQueue(e.target.value as QueueKey)}
            aria-label="Action queue"
            title="Morning-shift action queues. Reduced-confidence needs subgroup flags in the fleet snapshot (not yet available)."
          >
            {QUEUES.map((q) => (
              <option key={q.key} value={q.key} disabled={q.disabled} title={q.note}>
                {q.label}
              </option>
            ))}
          </select>
          <select
            value={preset}
            onChange={(e) => applyPreset(e.target.value)}
            aria-label="Sort preset"
            title="P(turn) is maintenance behaviour — not an engineering limit. Wear and condemning are engineering signals."
          >
            {PRESETS.map((p) => (
              <option key={p.key} value={p.key} title={p.note}>{p.label}</option>
            ))}
          </select>
          <button className="btn" onClick={exportCsv}>Export CSV</button>
          {caps?.action_ladder && !caps.action_ladder.ready && (
            <span
              className="chip"
              title={`Action ladder (${caps.action_ladder.status}): attention / plan-turn / turn-now thresholds await C&W sign-off. Only condemning limits are approved; no tier is derived until then.`}
            >
              action ladder: pending C&W
            </span>
          )}
          <button
            className="btn"
            disabled={wlBusy}
            onClick={() => { setWlBusy(true); exportWorklist().finally(() => setWlBusy(false)); }}
            title="Capacity-aware morning worklist: top-10 wheelsets per shed by calibrated 90d P(turn) — one shed cannot crowd out the rest"
          >
            {wlBusy ? "Worklist…" : "Worklist (top-10/shed)"}
          </button>
          {wlErr && <span className="muted small" style={{ color: "var(--danger)" }}>{wlErr}</span>}
          <select value={shed} onChange={(e) => { setShed(e.target.value); setPage(1); clearQueue(); }}>
            <option value="">Shed: all</option>
            {sheds.slice(0, 40).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select value={locoType} onChange={(e) => { setLocoType(e.target.value); setPage(1); clearQueue(); }}>
            <option value="">Loco type: all</option>
            {Array.from(new Set(rows.map((r) => r.loco_type).filter(Boolean))).map((t) => (
              <option key={t} value={t ?? ""}>{t}</option>
            ))}
          </select>
          <select value={limitingDim} onChange={(e) => { setLimitingDim(e.target.value); setPage(1); clearQueue(); }}>
            {LIMITING_DIMS.map((d) => (
              <option key={d} value={d}>{d ? `Limiting: ${d}` : "Limiting: all"}</option>
            ))}
          </select>
          <select value={riskLevel} onChange={(e) => { setRiskLevel(e.target.value); setPage(1); clearQueue(); }}>
            {RISK_LEVELS.map((l) => (
              <option key={l} value={l}>{l ? `Risk: ${l}` : "Risk: all"}</option>
            ))}
          </select>
        </div>

        {activeQueue && activeQueue.key !== "all" && (
          <p className="muted small queue-note">
            <b>Action queue — {activeQueue.label}:</b> {activeQueue.note}
          </p>
        )}

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
                  <th
                    onClick={() => toggleSort("pturn_90d")}
                    className="sortable"
                    aria-sort={sortBy === "pturn_90d" ? (descending ? "descending" : "ascending") : "none"}
                    title="primary ranking = calibrated 90d P(turn) (Phase 4 Target B, empirical realized rate)"
                  >
                    P(turn) 90d* {sortBy === "pturn_90d" ? (descending ? "↓" : "↑") : ""}
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
                  <th onClick={() => toggleSort("mean_wsmFlange")} className="sortable" aria-sort={sortBy === "mean_wsmFlange" ? (descending ? "descending" : "ascending") : "none"}>
                    Flange {sortBy === "mean_wsmFlange" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("mean_wsmRoot")} className="sortable" aria-sort={sortBy === "mean_wsmRoot" ? (descending ? "descending" : "ascending") : "none"}>
                    Root {sortBy === "mean_wsmRoot" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("mean_wsmThread")} className="sortable" aria-sort={sortBy === "mean_wsmThread" ? (descending ? "descending" : "ascending") : "none"}>
                    Thread {sortBy === "mean_wsmThread" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th>Limiting</th>
                  <th>Wear band</th>
                  <th onClick={() => toggleSort("days_to_condemning_dia")} className="sortable" aria-sort={sortBy === "days_to_condemning_dia" ? (descending ? "descending" : "ascending") : "none"}>
                    Condemning {sortBy === "days_to_condemning_dia" ? (descending ? "↓" : "↑") : ""}
                  </th>
                  <th onClick={() => toggleSort("staleness_days")} className="sortable" aria-sort={sortBy === "staleness_days" ? (descending ? "descending" : "ascending") : "none"}>
                    Staleness {sortBy === "staleness_days" ? (descending ? "↓" : "↑") : ""}
                  </th>
                </tr>
              </thead>
              <tbody ref={tbodyRef}>
                {rows.map((r, i) => {
                  const cal = r.pturn_90d_calibrated ?? r.pturn_90d;
                  const rowRisk = cal != null && cal >= 0.05 ? " risk-row-high" : cal != null && cal >= 0.01 ? " risk-row-mid" : "";
                  return (
                  <tr
                    key={r.wheelset_equipment_id}
                    data-i={i}
                    tabIndex={i === focusedIdx ? 0 : -1}
                    aria-selected={i === focusedIdx}
                    className={`clickable${rowRisk} ${i === focusedIdx ? "focused" : ""}`}
                    onClick={() => onSelect(r.wheelset_equipment_id, r.loco_number ?? undefined)}
                    onKeyDown={(e) => onRowKey(e, i)}
                  >
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_90d_calibrated ?? r.pturn_90d} raw={r.pturn_90d} decile={r.pturn_90d_decile} />
                    </td>
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_60d_calibrated ?? r.pturn_60d} raw={r.pturn_60d} decile={r.pturn_60d_decile} />
                    </td>
                    <td className="risk-cell">
                      <PturnCell v={r.pturn_30d_calibrated ?? r.pturn_30d} raw={r.pturn_30d} decile={r.pturn_30d_decile} />
                    </td>
                    <td>{r.loco_number ?? "—"}</td>
                    <td className="mono">#{r.wheelset_equipment_id}</td>
                    <td>{r.shed_any ?? "—"}</td>
                    <td>{fmt(r.mean_wsmFlange)}</td>
                    <td>{fmt(r.mean_wsmRoot)}</td>
                    <td>{fmt(r.mean_wsmThread)}</td>
                    <td><LimitChip dim={r.limiting_dim} /></td>
                    <td><WearBands bands={r.wear_bands} /></td>
                    <td>{fmt(r.days_to_condemning_dia, 0)} d</td>
                    <td>{fmt(r.staleness_days, 0)} d</td>
                  </tr>
                );})}
              </tbody>
            </table>
            <p className="muted small table-footnote">
              <span className="mono">P(turn)*</span> = calibrated 90d/60d/30d realized event rate (Phase 4
              reliability band, decile of the raw model score). The fleet is ranked by calibrated 90d P(turn)
              <span className="mono"> (Target B)</span>; raw XGB scores and deciles are in the row tooltip.
              Wear band (F/R/T) is a display-only margin convention against the approved Wrpld limits
              (flange 3.0 / root 6.0 / tread 6.5 mm) — never a sorting or condemning threshold.
            </p>
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
