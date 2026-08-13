import { useEffect, useState } from "react";
import { api } from "./api";
import type { FleetBacktest, WheelsetReplay } from "./types";

const DIMM = ["wsmRoot", "wsmFlange", "wsmThread", "wsmDia"];

export function BacktestView({ wheelsetId }: { wheelsetId: number }) {
  const [asof, setAsof] = useState<string>("2025-04-13");
  const [replay, setReplay] = useState<WheelsetReplay | null>(null);
  const [fleet, setFleet] = useState<FleetBacktest | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .fleetBacktest()
      .then(setFleet)
      .catch((e) => setErr((e as Error).message));
  }, []);

  useEffect(() => {
    setReplay(null);
    api
      .wheelsetBacktest(wheelsetId, asof)
      .then(setReplay)
      .catch((e) => setErr((e as Error).message));
  }, [wheelsetId, asof]);

  const implausible = replay?.degradation.filter((f) => f.implausibility_flag) ?? [];

  return (
    <div className="backtest">
      <section className="replay">
        <h3>Wheelset replay · as-of date</h3>
        <label className="asof">
          As-of (historical anchor):
          <input type="date" value={asof} onChange={(e) => setAsof(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        {replay && (
          <div className="replay-body">
            <p className="muted small">
              Anchor {replay.anchor?.slice(0, 10)} · strict point-in-time features ·
              compared to actual future observations.
            </p>

            <h4>Degradation — predicted vs actual</h4>
            <table>
              <thead>
                <tr>
                  <th>dim</th>
                  <th>H</th>
                  <th>current</th>
                  <th>predicted</th>
                  <th>actual</th>
                  <th>obs ts</th>
                  <th>MAE</th>
                  <th>flag</th>
                </tr>
              </thead>
              <tbody>
                {DIMM.flatMap((dim) => [30, 90, 180].map((h) => ({ dim, h }))).map(({ dim, h }) => {
                  const f = replay.degradation.find(
                    (x) => x.dim === dim && x.horizon === h
                  );
                  if (!f) return null;
                  return (
                    <tr key={`${dim}-${h}`} className={f.implausibility_flag ? "flag-row" : ""}>
                      <td>{dim}</td>
                      <td>{h}d</td>
                      <td>{f.current ?? "—"}</td>
                      <td>{f.predicted ?? "—"}</td>
                      <td>{f.observed_in_horizon ? f.actual : "—"}</td>
                      <td>{f.actual_ts ?? "—"}</td>
                      <td>{f.mae != null ? f.mae : "—"}</td>
                      <td>{f.implausibility_flag ?? ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {implausible.length > 0 && (
              <div className="warn">
                <strong>Implausibility flags ({implausible.length}):</strong>
                <ul>
                  {implausible.map((f, i) => (
                    <li key={i}>
                      {f.dim}@{f.horizon}d current={f.current} predicted={f.predicted}
                      {"> "}
                      {f.implausibility_flag}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <h4>Turning probability — raw P(turn) vs actual</h4>
            <table>
              <thead>
                <tr>
                  <th>horizon</th>
                  <th>P(turn) raw</th>
                  <th>P(turn) %</th>
                  <th>fleet rate</th>
                  <th>actual turned</th>
                  <th>n events</th>
                </tr>
              </thead>
              <tbody>
                {replay.turn_probability.map((p) => (
                  <tr key={p.horizon} className={p.actual_turned ? "flag-row" : ""}>
                    <td>{p.horizon}d</td>
                    <td>{p.probability_raw.toExponential(2)}</td>
                    <td>{p.probability_pct}%</td>
                    <td>{((p.turn_rate_train ?? 0) * 100).toFixed(1)}%</td>
                    <td>{p.actual_turned == null ? "—" : String(p.actual_turned)}</td>
                    <td>{p.actual_n_events}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="fleet">
        <h3>Fleet-level temporal backtest</h3>
        {!fleet && <p className="muted">loading…</p>}
        {fleet && (
          <FleetTable fleet={fleet} />
        )}
      </section>
    </div>
  );
}

function FleetTable({ fleet }: { fleet: FleetBacktest }) {
  const h90 = fleet.turn_probability?.horizons?.["90"]?.models;
  return (
    <div>
      <p className="muted small">
        {fleet.split} · {fleet.implausibility_note}
      </p>

      <h4>P(turn) — 90d (C1 XGB vs baselines)</h4>
      {h90 ? (
        <table>
          <thead>
            <tr>
              <th>model</th>
              <th>ROC-AUC</th>
              <th>PR-AUC</th>
              <th>Brier</th>
              <th>ECE</th>
              <th>capture top1%</th>
              <th>capture top5%</th>
              <th>capture top10%</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(h90).map(([name, m]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{m.roc_auc}</td>
                <td>{m.pr_auc}</td>
                <td>{m.brier}</td>
                <td>{m.ece}</td>
                <td>{m.capture?.["top1%"]?.share_of_turns ?? "—"}</td>
                <td>{m.capture?.["top5%"]?.share_of_turns ?? "—"}</td>
                <td>{m.capture?.["top10%"]?.share_of_turns ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">no 90d horizon data</p>
      )}

      <h4>Implausibility diagnostics (model vs actual, %)</h4>
      <table>
        <thead>
          <tr>
            <th>dim</th>
            <th>H</th>
            <th>type</th>
            <th>actual rate</th>
            <th>model rate</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(fleet.implausibility_diagnostics).flatMap(([dim, hs]) =>
            Object.entries(hs).map(([h, d]) => (
              <tr key={`${dim}-${h}`}>
                <td>{dim}</td>
                <td>{h}</td>
                <td>{d.flag}</td>
                <td>{d.actual_rate}%</td>
                <td className={d.model_rate > d.actual_rate ? "over" : ""}>
                  {d.model_rate}%
                </td>
                <td>{d.n}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
