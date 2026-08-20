import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Capabilities, LocoWheelsetTable, WheelAttribution, WheelsetDetail } from "./types";
import { AxleMap } from "./AxleMap";
import { BacktestView } from "./BacktestView";
import { LimitChip, WearBands } from "./LimitChip";
import { LocoSwitcher } from "./LocoSwitcher";
import { OverlayPanel } from "./OverlayPanel";
import { TrajectoryPanel } from "./TrajectoryPanel";
import { EmptyState, ErrorState, SkeletonBlock } from "./States";
function fmt(v: number | null | undefined, d = 2): string {
  return v == null || !isFinite(v) ? "—" : v.toFixed(d);
}
function pct(v: number | null | undefined): string {
  return v == null || !isFinite(v) ? "—" : (v * 100).toFixed(1) + "%";
}

export function LocoView({
  loco,
  caps,
  preselectWs,
  onWsChange,
  onNavigateLoco,
  onBack,
}: {
  loco: string;
  caps: Capabilities | null;
  preselectWs?: number | null;
  onWsChange?: (ws: number) => void;
  onNavigateLoco?: (locoNumber: string) => void;
  onBack: () => void;
}) {
  const [table, setTable] = useState<LocoWheelsetTable | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<WheelsetDetail | null>(null);
  const [view, setView] = useState<"overview" | "backtest">("overview");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [scope, setScope] = useState<"recent" | "all">("recent");
  const [showOverlay, setShowOverlay] = useState(false);
  const [overlayHover, setOverlayHover] = useState<number | null>(null);

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
        setScope("recent");
        const candidates = t.wheelsets.length > 0
          ? t.wheelsets
          : (t.wheelsets_all ?? []);
        if (candidates.length > 0) {
          if (preselectWs != null && candidates.some((w) => w.wheelset_equipment_id === preselectWs)) {
            setSelected(preselectWs);
          } else {
            setSelected(candidates[0].wheelset_equipment_id);
          }
        }
        if (t.wheelsets.length === 0 && (t.wheelsets_all ?? []).length > 0) {
          setScope("all");
        }
      })
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [loco, reload, preselectWs]);

  useEffect(() => {
    if (selected == null) return;
    setDetail(null);
    api
      .wheelsetOverview(selected)
      .then(setDetail)
      .catch((e) => setErr((e as Error).message));
  }, [selected]);

  // keep the URL hash in sync with the selected wheelset (?ws=) so reload/back restore it
  useEffect(() => {
    if (selected != null && onWsChange) onWsChange(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const rows = useMemo(() => {
    if (scope === "recent" || !table?.wheelsets_all) return table?.wheelsets ?? [];
    const all = table.wheelsets_all;
    return [...all.filter((w) => w.is_recently_measured), ...all.filter((w) => !w.is_recently_measured)];
  }, [table, scope]);

  const allCount = table?.wheelsets_all?.length ?? table?.wheelsets.length ?? 0;

  return (
    <div className="loco-page">
      {err && !loading && <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />}

      {loading && !table && <SkeletonBlock lines={4} />}

      {table && (
        <div className="loco-header">
          <div className="kpi">
            <span className="kpi-label">Loco</span>
            <span className="kpi-value">{table.loco_number}</span>
          </div>
          {onNavigateLoco && (
            <div className="kpi kpi-switcher">
              <LocoSwitcher loco={loco} onNavigate={onNavigateLoco} />
            </div>
          )}
          <div className="kpi">
            <span className="kpi-label">Type</span>
            <span className="kpi-value">{table.loco_type ?? "—"}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Recent wheelsets</span>
            <span className="kpi-value">
              {table.n_wheelsets}
              {table.n_wheelsets_current !== undefined && table.n_wheelsets_historical !== undefined && table.n_wheelsets_historical > 0 && (
                <>
                  {" "}
                  <span className="muted" title={`${table.n_wheelsets} recently measured (≤${table.recency_threshold_days}d, latest measurement still stamped this loco) · ${table.n_wheelsets_historical} older on record`}>
                    (+{table.n_wheelsets_historical})
                  </span>
                </>
              )}
            </span>
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

      {table && rows.length === 0 && (
        <EmptyState
          title={`No wheelsets for loco ${loco}`}
          hint="Check the loco number — it may be inactive or have no measurements."
        />
      )}

      {table && rows.length > 0 && (
        <section className="loco-table-wrap">
          <div className="loco-table-bar">
            <div>
              <h3>
                Wheelsets ({rows.length}
                {table.n_wheelsets_historical !== undefined && table.n_wheelsets_historical > 0 && scope === "recent"
                  ? ` of ${table.n_wheelsets_historical + rows.length} on record`
                  : ""})
              </h3>
              <p className="muted small">
                {scope === "recent"
                  ? `Showing recently measured (≤${table.recency_threshold_days}d) — a recency signal, not a confirmed equipment fit.`
                  : "All wheelsets ever measured on this loco; recent first, historical greyed."}
              </p>
            </div>
            <div>
              {table.snapshot_sourced && (
                <span className="chip">snapshot-sourced forecasts</span>
              )}
              <button className="nav-item back" onClick={onBack}>← Back to fleet</button>
            </div>
          </div>
          <div className="loco-table-bar">
            <button
              className={scope === "recent" ? "btn btn-primary" : "btn"}
              onClick={() => setScope("recent")}
            >
              Recent ({table.wheelsets.length})
            </button>
            <button
              className={scope === "all" ? "btn btn-primary" : "btn"}
              onClick={() => setScope("all")}
            >
              All history ({allCount})
            </button>
            {table.n_expected_axles != null && (
              <span
                className={`chip ${table.wheelsets.length < table.n_expected_axles ? "chip-reduced" : ""}`}
                title={
                  table.wheelsets.length < table.n_expected_axles
                    ? "Some axles have no recent measurement — under-counted, not necessarily missing wheels."
                    : "All expected axles have a recent measurement."
                }
              >
                measured {table.wheelsets.length} of {table.n_expected_axles} expected axles
              </span>
            )}
            <button
              className={showOverlay ? "btn btn-primary" : "btn"}
              onClick={() => setShowOverlay((s) => !s)}
              title="Superimpose the wear paths of all wheelsets on one chart"
            >
              {showOverlay ? "Hide overlay" : "Travel overlay"}
            </button>
          </div>
          <AxleMap
            rows={table.wheelsets_all ?? rows}
            selected={selected}
            onSelect={(ws) => {
              if (scope === "recent" && !table.wheelsets.some((w) => w.wheelset_equipment_id === ws)) {
                setScope("all");
              }
              setSelected(ws);
            }}
          />
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
                    <th>Wear band</th>
                    <th>Condemning</th>
                    <th title="calibrated 90d P(turn) — Phase 4 Target B realized rate">P(turn) 90d</th>
                    <th>Fc root 90d</th>
                    <th>Fc flange 90d</th>
                    <th>Fc tread 90d</th>
                    <th>Turns</th>
                    <th>Measured</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((w) => (
                    <tr
                      key={w.wheelset_equipment_id}
                      className={`clickable ${w.wheelset_equipment_id === selected ? "selected" : ""} ${overlayHover === w.wheelset_equipment_id ? "focused" : ""} ${scope === "all" && !w.is_recently_measured ? "historical" : ""}`}
                      onClick={() => setSelected(w.wheelset_equipment_id)}
                      onMouseEnter={() => setOverlayHover(w.wheelset_equipment_id)}
                      onMouseLeave={() => setOverlayHover((h) => (h === w.wheelset_equipment_id ? null : h))}
                    >
                      <td className="mono">#{w.wheelset_equipment_id}</td>
                      <td>{fmt(w.wheel_position_1_12, 0)}</td>
                      <td>{fmt(w.latest_mean_wsmDia)}</td>
                      <td>{fmt(w.latest_mean_wsmFlange)}</td>
                      <td>{fmt(w.latest_mean_wsmRoot)}</td>
                      <td>{fmt(w.latest_mean_wsmThread)}</td>
                      <td><LimitChip dim={w.limiting_dim} /></td>
                      <td><WearBands bands={w.wear_bands} /></td>
                      <td>{fmt(w.days_to_condemning_dia, 0)} d</td>
                      <td>
                        {(() => {
                          const p = w.pturn_90d_calibrated ?? w.pturn_90d;
                          return (
                            <span
                              className={p != null && p >= 0.01 ? "risk-high" : "risk-low"}
                              title={w.pturn_90d != null ? `raw score ${(w.pturn_90d * 100).toFixed(2)}% · calibrated ${w.pturn_90d_calibrated != null ? ((w.pturn_90d_calibrated * 100).toFixed(2) + "%") : "—"}${w.pturn_90d_decile != null ? ` · decile ${w.pturn_90d_decile}/9` : ""}` : undefined}
                            >
                              {pct(p)}
                            </span>
                          );
                        })()}
                      </td>
                      <td>{fmt(w.fc_wsmRoot_90d)}</td>
                      <td>{fmt(w.fc_wsmFlange_90d)}</td>
                      <td>{fmt(w.fc_wsmThread_90d)}</td>
                      <td>{w.n_turns}</td>
                      <td title={w.latest_measurement ?? undefined}>{w.staleness_days != null ? `${fmt(w.staleness_days, 0)} d ago` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        </section>
      )}

      {showOverlay && table && (
        <OverlayPanel wheelsets={rows} onHover={setOverlayHover} />
      )}

      {selected != null && (
        <main className="detail">
          {view === "overview" ? (
            detail ? (
              <WheelsetView detail={detail} caps={caps} />
            ) : (
              <SkeletonBlock lines={6} />
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

  const [attribution, setAttribution] = useState<WheelAttribution | null>(null);
  useEffect(() => {
    setAttribution(null);
    api
      .wheelsetAttribution(detail.wheelset_equipment_id, "turn")
      .then(setAttribution)
      .catch(() => setAttribution(null)); // not in the phase 4 scored batch -> hide the line
  }, [detail.wheelset_equipment_id]);

  // engineering warnings surfaced from forecast flags + subgroup flags
  const warnings: string[] = [];
  const subgroupGroups = new Set<string>();
  for (const f of detail.forecasts) {
    if (f.implausibility_flag) warnings.push(`${f.dim} @ ${f.horizon}d: ${f.implausibility_flag}`);
    for (const s of f.subgroup_flags ?? []) subgroupGroups.add(`${f.dim} ${s.group}`);
  }
  const reducedConfidence = subgroupGroups.size > 0;

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

      {warnings.length > 0 && (
        <div className="warn warn-engineering">
          <strong>Engineering warnings</strong>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
            {reducedConfidence && (
              <li>
                Reduced-confidence subgroup: {Array.from(subgroupGroups).join(", ")} — point
                forecasts shown, not decision-grade.
              </li>
            )}
          </ul>
        </div>
      )}

      <section className="forecast">
        <TrajectoryPanel wheelsetId={detail.wheelset_equipment_id} />
      </section>

      {diaFix && (
        <section className="pturn">
          <h3>Turning probability (P<sub>turn</sub>)</h3>
          <div className="pturn-cards">
            {detail.turn_probabilities.map((p) => (
              <div className="pturn-card" key={p.horizon}>
                <span className="pturn-h">{p.horizon}d</span>
                <span className="pturn-p">{((p.probability ?? 0) * 100).toFixed(1)}%</span>
                <span className="pturn-base">fleet rate {((p.turn_rate_train ?? 0) * 100).toFixed(1)}%</span>
                {p.calibrated_probability != null && p.conf_decile != null && (
                  <span className="pturn-rel">
                    realized ~{((p.calibrated_probability ?? 0) * 100).toFixed(1)}% 90d (decile {p.conf_decile}/9, Phase 4)
                  </span>
                )}
                {p.calibrated_probability == null && p.roc_auc != null && (
                  <span className="pturn-rel">backtest ROC-AUC {(p.roc_auc * 100).toFixed(1)}%</span>
                )}
              </div>
            ))}
          </div>
          {attribution && attribution.contributors.length > 0 && (
            <p className="muted small">
              <strong>Likely contributors</strong> (SHAP, Phase 4 attribution):{" "}
              {attribution.contributors
                .slice(0, 4)
                .map((c) => c.label)
                .join(" · ")}
              {attribution.probability != null &&
                ` — Phase 4 90d P(turn) ~${((attribution.probability ?? 0) * 100).toFixed(1)}%`}
              {attribution.conf_empirical_rate != null && attribution.conf_decile != null &&
                ` (realized ~${((attribution.conf_empirical_rate ?? 0) * 100).toFixed(1)}%, decile ${attribution.conf_decile}/9)`}
            </p>
          )}
          <p className="muted small">
            Estimated turning probability from historical maintenance behaviour – not a mandatory
            turning recommendation. Raw model score; "realized" is the empirical event rate of the
            score's decile (Phase 4 reliability band). Attribution is model attribution, never
            "cause" (contract §8).
          </p>
        </section>
      )}

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
                <th>dia cut</th>
              </tr>
            </thead>
            <tbody>
              {detail.turns.map((t, i) => (
                <tr key={i}>
                  <td>{t.post_ts.slice(0, 10)}</td>
                  <td>{t.delta_wsmDia ?? "—"}</td>
                  <td>{t.pre_wsmDia ?? "—"}</td>
                  <td>{t.post_wsmDia ?? "—"}</td>
                  <td>{t.dia_cut ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
