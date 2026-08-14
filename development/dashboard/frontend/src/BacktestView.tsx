import { useEffect, useState } from "react";
import { api } from "./api";
import type { Capabilities, FleetBacktest, OperationalCapture, WheelsetReplay } from "./types";

const DIMM = ["wsmRoot", "wsmFlange", "wsmThread", "wsmDia"];
const HORIZONS = [30, 90, 180];

function fmtNum(v: number | undefined | null, d = 3): string {
  return v == null || !isFinite(v) ? "—" : v.toFixed(d);
}

export function BacktestView({ wheelsetId, caps }: { wheelsetId: number; caps: Capabilities | null }) {
  const [asof, setAsof] = useState<string>("2025-04-13");
  const [replay, setReplay] = useState<WheelsetReplay | null>(null);
  const [fleet, setFleet] = useState<FleetBacktest | null>(null);
  const [capture, setCapture] = useState<OperationalCapture | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .fleetBacktest()
      .then(setFleet)
      .catch((e) => setErr((e as Error).message));
    api
      .fleetCapture()
      .then(setCapture)
      .catch(() => {}); // capture@k is optional enrichment, not a hard dependency
  }, []);

  useEffect(() => {
    setReplay(null);
    api
      .wheelsetBacktest(wheelsetId, asof)
      .then(setReplay)
      .catch((e) => setErr((e as Error).message));
  }, [wheelsetId, asof]);

  const implausible = replay?.degradation.filter((f) => f.implausibility_flag) ?? [];
  const diaFix = caps?.p0_2_dia_fix ?? false;

  return (
    <div className="backtest">
      <section className="replay">
        <h3>Wheelset replay · as-of date</h3>
        <label className="asof">
          As-of (historical anchor):
          <input type="date" value={asof} onChange={(e) => setAsof(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        {!caps && <p className="muted small">…checking serving capabilities</p>}
        {caps && !diaFix && (
          <div className="warn">
            <strong>Replay forecasts hidden (safe mode).</strong> The P0.2 diameter fix is not
            deployed — degradation forecasts are not renderable as engineering outputs.
          </div>
        )}
        {replay && (
          <div className="replay-body">
            <p className="muted small">
              Anchor {replay.anchor?.slice(0, 10)} · strict point-in-time features ·
              compared to actual future observations.
            </p>

            {replay.time_to_limit_summary && (
              <div className="ttl-summary">
                <span className="chip">
                  days to condemning (dia):{" "}
                  {replay.time_to_limit_summary.days_to_limit_point != null ? (
                    <>
                      <b>
                        {replay.time_to_limit_summary.days_to_limit_point.toFixed(0)} d
                      </b>
                      {replay.time_to_limit_summary.days_to_limit_lo != null && (
                        <>
                          {" "}
                          <span className="muted">
                            (band{" "}
                            {replay.time_to_limit_summary.days_to_limit_lo.toFixed(0)}–
                            {replay.time_to_limit_summary.days_to_limit_hi != null
                              ? replay.time_to_limit_summary.days_to_limit_hi.toFixed(0)
                              : "∞"}{" "}
                            d)
                          </span>
                        </>
                      )}
                    </>
                  ) : (
                    <span className="muted">
                      beyond 180 d horizon
                      {replay.time_to_limit_summary.status === "at_limit" ? " — at limit now" : ""}
                    </span>
                  )}{" "}
                  · limit {replay.time_to_limit_summary.limit_mm?.toFixed(0)} mm (hard stop)
                </span>
                <span className="muted small">
                  {replay.time_to_limit_summary.note}
                </span>
              </div>
            )}

            {diaFix && <>
              <h4>Degradation — predicted vs actual</h4>
              <ReplayDegradationTable replay={replay} />
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
            </>}

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
        {capture && <CaptureTable capture={capture} />}
      </section>
    </div>
  );
}

function ReplayDegradationTable({ replay }: { replay: WheelsetReplay }) {
  const [sortByTtl, setSortByTtl] = useState(false);
  const rows = DIMM.flatMap((dim) => HORIZONS.map((h) => ({ dim, h })))
    .map(({ dim, h }) => {
      const f = replay.degradation.find((x) => x.dim === dim && x.horizon === h);
      return f ? { f } : null;
    })
    .filter((r): r is { f: WheelsetReplay["degradation"][number] } => r != null);

  const sorted = sortByTtl
    ? [...rows].sort((a, b) => {
        const da = replay.time_to_limit[a.f.dim]?.days_to_limit_point;
        const db = replay.time_to_limit[b.f.dim]?.days_to_limit_point;
        const va = da == null ? Infinity : da;
        const vb = db == null ? Infinity : db;
        return va - vb;
      })
    : rows;

  return (
    <div>
      <div className="table-toolbar">
        <label>
          <input
            type="checkbox"
            checked={sortByTtl}
            onChange={(e) => setSortByTtl(e.target.checked)}
          />
          sort by soonest days-to-condemning
        </label>
      </div>
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
            <th>days to condemning</th>
            <th>flag</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(({ f }) => {
            const ttl = replay.time_to_limit[f.dim];
            const reduced = f.subgroup_flags.length > 0;
            const cls = [
              f.implausibility_flag ? "flag-row" : "",
              reduced ? "subgroup-row" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <tr key={`${f.dim}-${f.horizon}`} className={cls}>
                <td>{f.dim}</td>
                <td>{f.horizon}d</td>
                <td>{f.current ?? "—"}</td>
                <td>{f.predicted ?? "—"}</td>
                <td>{f.observed_in_horizon ? f.actual : "—"}</td>
                <td>{f.actual_ts ?? "—"}</td>
                <td>{f.mae != null ? f.mae : "—"}</td>
                <td>
                  {ttl && ttl.days_to_limit_point != null ? (
                    <span className={`chip${reduced ? " chip-reduced" : ""}`}>
                      {ttl.days_to_limit_point.toFixed(0)} d
                      {ttl.days_to_limit_lo != null && (
                        <span className="muted">
                          {" "}
                          (band {ttl.days_to_limit_lo.toFixed(0)}–
                          {ttl.days_to_limit_hi != null ? ttl.days_to_limit_hi.toFixed(0) : "∞"})
                        </span>
                      )}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {f.implausibility_flag ?? ""}
                  {reduced && (
                    <span
                      className="flag flag-reduced"
                      title={f.subgroup_flags
                        .map((s) => `${s.group}:${s.level} · ${s.reason}`)
                        .join("\n")}
                    >
                      ⚠ reduced confidence
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DegradationDeltaTable({ fleet }: { fleet: FleetBacktest }) {
  const staticGrid = fleet.degradation?.static;
  if (!staticGrid) {
    return <p className="muted">no static degradation grid in fleet backtest payload</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>dim</th>
          <th>H</th>
          <th>ΔMAE (mm)</th>
          <th>ΔR²</th>
          <th>Δρ</th>
          <th>n_test</th>
        </tr>
      </thead>
      <tbody>
        {DIMM.flatMap((dim) => HORIZONS.map((h) => ({ dim, h }))).map(({ dim, h }) => {
          const cell = staticGrid[dim]?.[`${h}d`];
          const m = cell?.models?.C1_xgb;
          if (!m) return null;
          return (
            <tr key={`${dim}-${h}`}>
              <td>{dim}</td>
              <td>{h}d</td>
              <td>{fmtNum(m.delta_mae)}</td>
              <td className={m.delta_r2 != null && m.delta_r2 > 0 ? "delta-good" : ""}>
                {fmtNum(m.delta_r2)}
              </td>
              <td>{fmtNum(m.delta_spearman)}</td>
              <td>{cell.n_test?.toLocaleString() ?? "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function CaptureTable({ capture }: { capture: OperationalCapture }) {
  const pctLabel = (k: string) => k.replace("capture_", "").replace("%", "%");
  return (
    <div className="capture">
      <h4>Operational capture@k — turn-within-H (flange/root/tread)</h4>
      <p className="muted small">{capture.label}</p>
      <table>
        <thead>
          <tr>
            <th>dim</th>
            <th>H</th>
            {capture.by_dim &&
              Object.values(capture.by_dim).flatMap((hs) =>
                Object.values(hs).flatMap((c) =>
                  Object.keys(c.capture ?? {})
                )
              ).filter((v, i, a) => a.indexOf(v) === i).map((k) => (
                <th key={k}>capture top {pctLabel(k)}</th>
              ))}
            <th>fleet turn rate</th>
            <th>n label</th>
          </tr>
        </thead>
        <tbody>
          {DIMM.filter((d) => d !== "wsmDia").flatMap((dim) =>
            HORIZONS.map((h) => ({ dim, h }))
          ).map(({ dim, h }) => {
            const cell = capture.by_dim?.[dim]?.[`${h}d`];
            if (!cell) return null;
            const keys = Object.keys(cell.capture ?? {});
            return (
              <tr key={`${dim}-${h}`}>
                <td>{dim}</td>
                <td>{h}d</td>
                {keys.map((k) => (
                  <td key={k} className={cell.capture[k] != null && cell.capture[k] >= 0.7 ? "capture-good" : ""}>
                    {cell.capture[k] != null
                      ? `${(cell.capture[k]! * 100).toFixed(0)}%`
                      : "—"}
                  </td>
                ))}
                <td>
                  {cell.turn_rate != null ? `${(cell.turn_rate * 100).toFixed(2)}%` : "—"}
                </td>
                <td>{cell.n_label.toLocaleString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">
        Success = confirmed lifecycle turn completes within H days; anchors ranked by
        predicted delta for that dim at that horizon. High capture@k means the ranked
        inspection list catches the wheelsets that actually got turned. P(turn) is a
        prioritisation launcher, never the sole ranking signal — this table measures
        the wear-risk ranking, not a mandate.
      </p>
      {capture.note && <p className="muted small">{capture.note}</p>}
    </div>
  );
}

export function FleetTable({ fleet }: { fleet: FleetBacktest }) {
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

      <h4>Degradation — Δ-space metrics, static grid (C1 XGB)</h4>
      <p className="muted small">
        ΔMAE == level MAE (level = anchor + Δ). The honest skill signal is ΔR² / Δρ —
        positive ΔR² means real change-prediction beyond persistence.
      </p>
      <DegradationDeltaTable fleet={fleet} />

      <h4>Degradation — Δ-space metrics, static grid (C1 XGB)</h4>
      <p className="muted small">
        ΔMAE == level MAE (level = anchor + Δ). The honest skill signal is ΔR² / Δρ —
        positive ΔR² means real change-prediction beyond persistence.
      </p>
      <DegradationDeltaTable fleet={fleet} />

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
