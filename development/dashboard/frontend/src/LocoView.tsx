import { useEffect, useState } from "react";
import { api } from "./api";
import type { Capabilities, LocoWheelsetTable, WheelsetDetail } from "./types";
import { WearTimeline } from "./WearTimeline";
import AllWheelPlots from "./AllWheelPlots";
import { BacktestView } from "./BacktestView";
import { TrajectoryPanel } from "./TrajectoryPanel";

function fmt(v: number | null | undefined, d = 2): string {
  return v == null || !isFinite(v) ? "—" : v.toFixed(d);
}
function pct(v: number | null | undefined): string {
  return v == null || !isFinite(v) ? "—" : (v * 100).toFixed(1) + "%";
}

export function LocoView({
  loco,
  caps,
  onBack,
}: {
  loco: string;
  caps: Capabilities | null;
  onBack: () => void;
}) {
  const [table, setTable] = useState<LocoWheelsetTable | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<WheelsetDetail | null>(null);
  const [view, setView] = useState<"overview" | "backtest">("overview");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    setTable(null);
    setSelected(null);
    setDetail(null);
    api
      .locoWheelsets(loco)
      .then((t) => {
        setTable(t);
        if (t.wheelsets.length > 0) {
          setSelected(t.wheelsets[0].wheelset_equipment_id);
        }
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [loco]);

  useEffect(() => {
    if (selected == null) return;
    setDetail(null);
    api
      .wheelsetOverview(selected)
      .then(setDetail)
      .catch((e) => setErr((e as Error).message));
  }, [selected]);

  return (
    <div className="loco-page">
      {err && <div className="error">{err}</div>}

      {loading && <p className="muted">Loading loco {loco}…</p>}

      {table && (
        <div className="loco-header">
          <div className="kpi">
            <span className="kpi-label">Loco</span>
            <span className="kpi-value">{table.loco_number}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Type</span>
            <span className="kpi-value">{table.loco_type ?? "—"}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Wheelsets</span>
            <span className="kpi-value">{table.n_wheelsets}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Segments</span>
            <span className="kpi-value">{table.n_segments}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Confirm turns</span>
            <span className="kpi-value">{table.n_turns}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Home shed</span>
            <span className="kpi-value">{table.home_shed ?? "—"}</span>
          </div>
        </div>
      )}

      {table && (
        <section className="loco-table-wrap">
          <div className="loco-table-bar">
            <h3>Wheelsets ({table.wheelsets.length})</h3>
            {table.snapshot_sourced && (
              <span className="chip">snapshot-sourced forecasts</span>
            )}
            <button className="nav-item back" onClick={onBack}>← Back to fleet</button>
          </div>
          <div className="table-wrap">
            <table className="risk-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Pos</th>
                  <th>Dia</th>
                  <th>Flange</th>
                  <th>Root</th>
                  <th>Thread</th>
                  <th>Limiting</th>
                  <th>Condemning</th>
                  <th>P(turn) 90d</th>
                  <th>Fc root 90d</th>
                  <th>Fc flange 90d</th>
                  <th>Fc tread 90d</th>
                  <th>Turns</th>
                  <th>Staleness</th>
                </tr>
              </thead>
              <tbody>
                {table.wheelsets.map((w) => (
                  <tr
                    key={w.wheelset_equipment_id}
                    className={`clickable ${w.wheelset_equipment_id === selected ? "selected" : ""}`}
                    onClick={() => setSelected(w.wheelset_equipment_id)}
                  >
                    <td className="mono">#{w.wheelset_equipment_id}</td>
                    <td>{fmt(w.wheel_position_1_12, 0)}</td>
                    <td>{fmt(w.latest_mean_wsmDia)}</td>
                    <td>{fmt(w.latest_mean_wsmFlange)}</td>
                    <td>{fmt(w.latest_mean_wsmRoot)}</td>
                    <td>{fmt(w.latest_mean_wsmThread)}</td>
                    <td>{w.limiting_dim ?? "—"}</td>
                    <td>{fmt(w.days_to_condemning_dia, 0)} d</td>
                    <td>
                      <span className={w.pturn_90d != null && w.pturn_90d >= 0.01 ? "risk-high" : "risk-low"}>
                        {pct(w.pturn_90d)}
                      </span>
                    </td>
                    <td>{fmt(w.fc_wsmRoot_90d)}</td>
                    <td>{fmt(w.fc_wsmFlange_90d)}</td>
                    <td>{fmt(w.fc_wsmThread_90d)}</td>
                    <td>{w.n_turns}</td>
                    <td>{fmt(w.days_since_turning, 0)} d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {selected != null && (
        <main className="detail">
          {view === "overview" ? (
            detail ? (
              <WheelsetView detail={detail} caps={caps} />
            ) : (
              <p className="hint">Loading wheelset…</p>
            )
          ) : (
            <BacktestView wheelsetId={selected} caps={caps} />
          )}
          <div className="tabs">
            <button className={view === "overview" ? "tab active" : "tab"} onClick={() => setView("overview")}>
              Overview
            </button>
            <button className={view === "backtest" ? "tab active" : "tab"} onClick={() => setView("backtest")}>
              Validation / Backtest
            </button>
          </div>
        </main>
      )}
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
          Profile evolution <span className="muted">({detail.measurements.length} measurements)</span>
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
