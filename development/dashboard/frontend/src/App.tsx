import { useEffect, useState } from "react";
import { api } from "./api";
import type { LocomotiveSummary, WheelsetDetail } from "./types";
import { WearTimeline } from "./WearTimeline";
import AllWheelPlots from "./AllWheelPlots";
import { BacktestView } from "./BacktestView";

export function App() {
  const [loco, setLoco] = useState<string>("37597");
  const [summary, setSummary] = useState<LocomotiveSummary | null>(null);
  const [detail, setDetail] = useState<WheelsetDetail | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"overview" | "backtest">("overview");

  async function search() {
    setError(null);
    setDetail(null);
    setSelected(null);
    setLoading(true);
    try {
      const s = await api.loco(loco.trim());
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

  return (
    <div className="app">
      <header className="topbar">
        <h1>Wheel Lifecycle Dashboard</h1>
        <div className="search">
          <input
            value={loco}
            onChange={(e) => setLoco(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            placeholder="Loco number e.g. 37597"
          />
          <button onClick={search} disabled={loading}>
            {loading ? "Loading…" : "Search"}
          </button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      {summary && (
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
      )}

      {summary && (
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
                <WheelsetView detail={detail} />
              ) : (
                <p className="hint">Select a wheelset to view details…</p>
              )
            ) : selected ? (
              <BacktestView wheelsetId={selected} />
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
      )}
    </div>
  );
}

function WheelsetView({ detail }: { detail: WheelsetDetail }) {
  const byDim = (dim: string) => detail.forecasts.filter((f) => f.dim === dim);
  const dims = ["wsmRoot", "wsmFlange", "wsmThread", "wsmDia"];

  return (
    <div className="wheelset-view">
      <h2>
        Wheelset #{detail.wheelset_equipment_id}
        {detail.loco_number ? ` · ${detail.loco_number}` : ""}
      </h2>
      {detail.latest_measurement && (
        <p className="muted">Latest measurement {detail.latest_measurement.slice(0, 10)}</p>
      )}

      <section className="forecast">
        <h3>Degradation forecasts (predicted profile state)</h3>
        <table>
          <thead>
            <tr>
              <th>dimension</th>
              <th>30d</th>
              <th>90d</th>
              <th>180d</th>
            </tr>
          </thead>
          <tbody>
            {dims.map((d) => (
              <tr key={d}>
                <td>{d}</td>
                {[30, 90, 180].map((h) => {
                  const f = byDim(d).find((x) => x.horizon === h);
                  return <td key={h}>{f?.value != null ? f.value.toFixed(3) : "—"}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          Model estimates from a point-in-time serving extractor, not engineering mandates.
        </p>
      </section>

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
