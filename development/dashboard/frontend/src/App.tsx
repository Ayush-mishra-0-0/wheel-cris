import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Capabilities, LocomotiveSummary, SearchHit, WheelsetDetail } from "./types";
import { WearTimeline } from "./WearTimeline";
import AllWheelPlots from "./AllWheelPlots";
import { BacktestView } from "./BacktestView";
import { TrajectoryPanel } from "./TrajectoryPanel";
import { FleetView } from "./FleetView";

type Page = "fleet" | "search" | "validation" | "loco";

export function App() {
  const [page, setPage] = useState<Page>("fleet");
  const [summary, setSummary] = useState<LocomotiveSummary | null>(null);
  const [detail, setDetail] = useState<WheelsetDetail | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"overview" | "backtest">("overview");
  const [caps, setCaps] = useState<Capabilities | null>(null);

  // global search (type-ahead)
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [showHits, setShowHits] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .config()
      .then(setCaps)
      .catch(() => setCaps(null));
  }, []);

  // debounced type-ahead from /fleet/search
  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .fleetSearch(q.trim())
        .then((r) => setHits(r.items.slice(0, 8)))
        .catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function openLoco(num: string) {
    setPage("loco");
    setError(null);
    setDetail(null);
    setSelected(null);
    setLoading(true);
    setShowHits(false);
    try {
      const s = await api.loco(num);
      setSummary(s);
      if (s.wheelsets.length > 0) {
        setSelected(s.wheelsets[0].wheelset_equipment_id);
      }
    } catch (e) {
      setSummary(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (selected == null) return;
    setDetail(null);
    api
      .wheelsetOverview(selected)
      .then(setDetail)
      .catch((e) => setError((e as Error).message));
  }, [selected]);

  function go(page: Page) {
    setPage(page);
    setError(null);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          Wheel Lifecycle Dashboard
        </div>
        <div className="global-search" ref={searchRef}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => setShowHits(true)}
            onBlur={() => setTimeout(() => setShowHits(false), 150)}
            onKeyDown={(e) => e.key === "Enter" && hits[0]?.loco_number && openLoco(hits[0].loco_number)}
            placeholder="Search loco / shed / type…"
          />
          {showHits && q.trim() && (
            <div className="search-hits">
              {hits.length === 0 ? (
                <div className="search-hit muted">No matches for “{q}”</div>
              ) : (
                hits.map((h, i) => (
                  <button
                    key={i}
                    className="search-hit"
                    onMouseDown={() => h.loco_number && openLoco(h.loco_number)}
                  >
                    <span className="search-hit-loco">{h.loco_number ?? "—"}</span>
                    <span className="muted small">
                      {h.shed ?? ""}
                      {h.shed ? " · " : ""}
                      {h.loco_type ?? ""} · {h.n_wheelsets} ws
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </header>

      <div className="shell">
        <aside className="sidebar">
          <nav>
            <button className={page === "fleet" ? "nav-item active" : "nav-item"} onClick={() => go("fleet")}>
              Fleet
            </button>
            <button
              className={page === "search" ? "nav-item active" : "nav-item"}
              onClick={() => {
                go("search");
                setShowHits(true);
                searchRef.current?.focus();
              }}
            >
              Search
            </button>
            <button
              className={page === "validation" ? "nav-item active" : "nav-item"}
              onClick={() => go("validation")}
            >
              Validation / Backtest
            </button>
          </nav>
          {page === "loco" && summary && (
            <div className="sidebar-sub">
              <button className="nav-item back" onClick={() => go("fleet")}>
                ← Back to fleet
              </button>
            </div>
          )}
        </aside>

        <main className="content">
          {error && <div className="error">{error}</div>}

          {page === "fleet" && (
            <FleetView
              onSelect={(ws, locoNumber) => {
                if (locoNumber) {
                  openLoco(locoNumber);
                } else {
                  setPage("loco");
                  setSelected(ws);
                }
              }}
            />
          )}

          {page === "search" && (
            <div className="search-page">
              <h2>Search</h2>
              <p className="muted">Type a loco number, shed or loco type in the top bar.</p>
              {hits.length > 0 && (
                <ul className="search-results">
                  {hits.map((h, i) => (
                    <li key={i}>
                      <button className="search-result" onClick={() => h.loco_number && openLoco(h.loco_number)}>
                        <b>{h.loco_number}</b>
                        <span className="muted">
                          {h.shed} · {h.loco_type} · {h.n_wheelsets} wheelsets
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {page === "validation" && (
            <div className="validation-page">
              <h2>Validation / Backtest</h2>
              <p className="muted small">
                Fleet-level metrics from <code>/backtest/fleet</code>. For wheelset-level replay,
                open a loco and use the wheelset tabs.
              </p>
              {selected != null ? (
                <BacktestView wheelsetId={selected} caps={caps} />
              ) : (
                <div className="warn">
                  No wheelset selected. Open a loco from Fleet or Search to run a replay backtest.
                </div>
              )}
            </div>
          )}

          {page === "loco" && loading && <p className="muted">Loading loco…</p>}

          {page === "loco" && !loading && summary && (
            <div className="loco-page">
              <div className="loco-header">
                <div className="kpi">
                  <span className="kpi-label">Loco</span>
                  <span className="kpi-value">{summary.loco_number}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-label">Type</span>
                  <span className="kpi-value">{summary.loco_type ?? "—"}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-label">Wheelsets</span>
                  <span className="kpi-value">{summary.n_wheelsets}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-label">Segments</span>
                  <span className="kpi-value">{summary.n_segments}</span>
                </div>
                <div className="kpi">
                  <span className="kpi-label">Confirm turns</span>
                  <span className="kpi-value">{summary.n_turns}</span>
                </div>
              </div>

              <div className="layout">
                <aside className="ws-list">
                  <h3>Wheelsets ({summary.wheelsets.length})</h3>
                  {summary.wheelsets.map((w) => (
                    <button
                      key={w.wheelset_equipment_id}
                      className={`ws-item ${w.wheelset_equipment_id === selected ? "active" : ""}`}
                      onClick={() => setSelected(w.wheelset_equipment_id)}
                    >
                      <span className="ws-id">#{w.wheelset_equipment_id}</span>
                      <span className="ws-sub">
                        dia {w.latest_mean_wsmDia?.toFixed(2)}
                        {" · "}
                        flg {w.latest_mean_wsmFlange?.toFixed(3)}
                        {" · "}
                        {w.n_turns} turns
                      </span>
                    </button>
                  ))}
                </aside>

                <main className="detail">
                  {view === "overview" ? (
                    detail ? (
                      <WheelsetView detail={detail} caps={caps} />
                    ) : (
                      <p className="hint">Select a wheelset to view details…</p>
                    )
                  ) : selected ? (
                    <BacktestView wheelsetId={selected} caps={caps} />
                  ) : (
                    <p className="hint">Select a wheelset to run a backtest…</p>
                  )}
                  {selected != null && (
                    <div className="tabs">
                      <button
                        className={view === "overview" ? "tab active" : "tab"}
                        onClick={() => setView("overview")}
                      >
                        Overview
                      </button>
                      <button
                        className={view === "backtest" ? "tab active" : "tab"}
                        onClick={() => setView("backtest")}
                      >
                        Validation / Backtest
                      </button>
                    </div>
                  )}
                </main>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function WheelsetView({ detail, caps }: { detail: WheelsetDetail; caps: Capabilities | null }) {
  const diaFix = caps?.p0_2_dia_fix ?? false;
  return (
    <div className="wheelset-view">
      <h2>
        Wheelset #{detail.wheelset_equipment_id}
        {detail.loco_number ? ` · ${detail.loco_number}` : ""}
      </h2>
      {detail.latest_measurement && (
        <p className="muted">Latest measurement {detail.latest_measurement.slice(0, 10)}</p>
      )}

      {!caps && <p className="muted small">…checking serving capabilities</p>}
      {caps && !diaFix && (
        <div className="warn">
          <strong>Forecasts hidden (safe mode).</strong> The P0.2 diameter fix is not deployed:
          serving models are not in delta mode, so degradation forecasts are not renderable as
          engineering outputs. History and turn records below are unaffected.
        </div>
      )}

      {diaFix && (
        <section className="forecast">
          <TrajectoryPanel wheelsetId={detail.wheelset_equipment_id} />
        </section>
      )}

      {diaFix && (
        <section className="pturn">
          <h3>Turning probability (P<sub>turn</sub>)</h3>
          <div className="pturn-cards">
            {detail.turn_probabilities.map((p) => (
              <div className="pturn-card" key={p.horizon}>
                <span className="pturn-h">{p.horizon}d</span>
                <span className="pturn-p">{((p.probability ?? 0) * 100).toFixed(1)}%</span>
                <span className="pturn-base">fleet rate {((p.turn_rate_train ?? 0) * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
          <p className="muted small">
            Estimated turning probability from historical maintenance behaviour – not a mandatory
            turning recommendation.
          </p>
        </section>
      )}

      <section className="history">
        <h3>
          Profile evolution{" "}
          <span className="muted">({detail.measurements.length} measurements)</span>
        </h3>
        <WearTimeline measurements={detail.measurements} />
      </section>

      {detail.loco_number && <AllWheelPlots loco={detail.loco_number} />}

      {detail.turns.length > 0 && (
        <section className="turns">
          <h3>Confirmed turning events ({detail.turns.length})</h3>
          <table>
            <thead>
              <tr>
                <th>post date</th>
                <th>dia Δ</th>
                <th>pre dia</th>
                <th>post dia</th>
              </tr>
            </thead>
            <tbody>
              {detail.turns.map((t, i) => (
                <tr key={i}>
                  <td>{t.post_ts.slice(0, 10)}</td>
                  <td>{t.delta_wsmDia ?? "—"}</td>
                  <td>{t.pre_wsmDia ?? "—"}</td>
                  <td>{t.post_wsmDia ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
