import { useEffect, useMemo, useState } from "react";
import * as echarts from "echarts";
import { EChart } from "./EChart";
import type { EChartsOption } from "./EChart";
import { api } from "./api";
import type { SegmentBand, TrajectoryContract, TrajectoryDim, TrajectoryForecast, TurnMarker } from "./types";
import { ErrorState, EmptyState, SkeletonBlock } from "./States";

const PRIMARY_DIMS = ["wsmFlange", "wsmRoot", "wsmThread"];
const DERIVED_DIMS = ["wsmDia"];
const COLORS: Record<string, string> = {
  wsmFlange: "#c4523a",
  wsmRoot: "#7a6a9e",
  wsmThread: "#3d7a54",
  wsmDia: "#4a7a9e",
};
const BAND_COLOR = "rgba(245, 166, 35, 0.14)";

function fmt(v: unknown, d = 2): string {
  const n = typeof v === "number" ? v : Number(v);
  return !isFinite(n) ? "—" : n.toFixed(d);
}

const PRE_VAL: Record<string, (t: TurnMarker) => number | null> = {
  wsmFlange: (t) => t.pre_wsmFlange,
  wsmRoot: (t) => t.pre_wsmRoot,
  wsmThread: (t) => t.pre_wsmThread,
  wsmDia: (t) => t.pre_wsmDia,
};

export function TrajectoryPanel({ wheelsetId }: { wheelsetId: number }) {
  const [data, setData] = useState<TrajectoryContract | null>(null);
  const [asof, setAsof] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [exporting, setExporting] = useState<string | null>(null);
  const [showDia, setShowDia] = useState(false); // primary-only default

  useEffect(() => {
    setLoading(true);
    setErr(null);
    setData(null);
    api
      .trajectory(wheelsetId, asof || undefined)
      .then(setData)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [wheelsetId, asof, reload]);

  const handleExport = async (format: "csv" | "png" | "svg") => {
    setExporting(format);
    try {
      const params = new URLSearchParams();
      params.set("format", format);
      if (asof) params.set("asof", asof);
      const url = `/api/v1/wheelset/${wheelsetId}/lifecycle/export?${params.toString()}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }
      const blob = await response.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `wheelset_${wheelsetId}_lifecycle.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setExporting(null);
    }
  };

  const dimOrder = showDia ? [...PRIMARY_DIMS, ...DERIVED_DIMS] : [...PRIMARY_DIMS];
  const hasForecasts = (data?.dims ?? []).some((d) => d.forecasts.length > 0);
  const noDims = data != null && data.dims.length === 0;

  return (
    <section className="trajectory">
      <h3>
        Wear trajectory{" "}
        <span className="muted">
          (flange / root / tread = primary · diameter derived)
        </span>
      </h3>
      <div className="asof">
        <label>
          As-of (historical re-anchor shows residual strip):
          <input
            type="date"
            value={asof}
            onChange={(e) => setAsof(e.target.value)}
          />
          {asof && (
            <button className="clear" onClick={() => setAsof("")}>
              latest
            </button>
          )}
        </label>
      </div>

      <div className="export-buttons">
        <label className="muted small">Export:</label>
        <button 
          onClick={() => handleExport("csv")} 
          disabled={exporting !== null}
          className="export-btn"
        >
          {exporting === "csv" ? "…" : "CSV"}
        </button>
        <button 
          onClick={() => handleExport("png")} 
          disabled={exporting !== null}
          className="export-btn"
        >
          {exporting === "png" ? "…" : "PNG"}
        </button>
        <button 
          onClick={() => handleExport("svg")} 
          disabled={exporting !== null}
          className="export-btn"
        >
          {exporting === "svg" ? "…" : "SVG"}
        </button>
      </div>

      <div className="dim-toggle">
        <button
          className={!showDia ? "btn btn-primary" : "btn"}
          onClick={() => setShowDia(false)}
          title="flange / root / tread — the wear dims that drive turning"
        >
          Primary only
        </button>
        <button
          className={showDia ? "btn btn-primary" : "btn"}
          onClick={() => setShowDia(true)}
          title="add the derived diameter diagnostic to the grid"
        >
          + dia
        </button>
      </div>

      {err && !loading && <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />}
      {loading && <SkeletonBlock lines={5} />}

      {noDims && !loading && !err && (
        <EmptyState
          title="No trajectory data for this wheelset"
          hint="No observed profile history is on record for this wheelset."
        />
      )}

      {data && !noDims && (
        <>
          {!hasForecasts && (
            <div className="banner banner-warn">
              Forecasts unavailable (safe mode / no serving output) — observed history only. The
              degradation models are not in delta mode, so 30/90/180 d forecasts are not rendered as
              engineering outputs.
            </div>
          )}
          {data.time_to_limit_summary && (
            <div className="ttl-summary">
              <span className="chip">
                days to condemning (dia):{" "}
                {data.time_to_limit_summary.days_to_limit_point != null ? (
                  <>
                    <b>{data.time_to_limit_summary.days_to_limit_point.toFixed(0)} d</b>
                    {data.time_to_limit_summary.days_to_limit_lo != null && (
                      <>
                        {" "}
                        <span className="muted">
                          (band {data.time_to_limit_summary.days_to_limit_lo.toFixed(0)}–
                          {data.time_to_limit_summary.days_to_limit_hi != null
                            ? data.time_to_limit_summary.days_to_limit_hi.toFixed(0)
                            : "∞"}{" "}
                          d)
                        </span>
                      </>
                    )}
                  </>
                ) : (
                  <span className="muted">
                    beyond 180 d horizon{data.time_to_limit_summary.status === "at_limit" ? " — at limit now" : ""}
                  </span>
                )}{" "}
                · limit {data.time_to_limit_summary.limit_mm?.toFixed(0)} mm (hard stop)
              </span>
              <span className="muted small">{data.time_to_limit_summary.note}</span>
            </div>
          )}
          {data.turn_reset && data.turn_reset.restore_claimed && (
            <div className="banner banner-restored">
              <strong>
                Anchor at lifecycle {data.turn_reset.boundary_kind ?? "boundary"}:
              </strong>{" "}
              the wear path continues from the restored (post-{data.turn_reset.boundary_kind}) level,
              not from the pre-{data.turn_reset.boundary_kind} state.
              {data.turn_reset.boundary_kind === "turn" &&
                data.turn_reset.cut_dia_mm != null && (
                  <> Diameter cut ≈ {data.turn_reset.cut_dia_mm.toFixed(2)} mm.</>
                )}{" "}
              <span className="muted small">
                Forecast = restored level + Δ, so the reset is not extrapolated as continuous wear.
              </span>
            </div>
          )}
          {data.limiting_dim_provenance && (
            <div className="provenance-row">
              <span className="muted small">
                Limiting dim:
              </span>
              <span className="chip">
                verified <b>{data.limiting_dim_provenance.limiting_dim_verified ?? "—"}</b>
              </span>
              <span
                className={`chip chip-source-${data.limiting_dim_provenance.limiting_dim_source ?? ""}`}
                title="recorded_reason = shed/register reason of turning; ratio_calibrated = fleet-calibrated bottleneck; predicted = forecast heuristic fallback"
              >
                source {data.limiting_dim_provenance.limiting_dim_source ?? "—"}
              </span>
              {data.limiting_dim_provenance.limiting_dim_heuristic &&
                data.limiting_dim_provenance.limiting_dim_verified &&
                data.limiting_dim_provenance.limiting_dim_heuristic !== data.limiting_dim_provenance.limiting_dim_verified && (
                  <span className="muted small">
                    heuristic says {data.limiting_dim_provenance.limiting_dim_heuristic}
                  </span>
                )}
              {data.limiting_dim_provenance.limiting_reason && (
                <span className="muted small">{data.limiting_dim_provenance.limiting_reason}</span>
              )}
            </div>
          )}
          <ForecastReadout
            data={data}
            showDia={showDia}
            reduced={new Set(
              data.dims.flatMap((d) =>
                d.forecasts.some((f) => (f.subgroup_flags ?? []).length > 0)
                  ? [d.dim]
                  : [],
              ),
            )}
          />
          <div className="trajectory-grid">
            {dimOrder.map((dim) => {
              const d = data.dims.find((x) => x.dim === dim);
              return d ? (
                <TrajectoryChart key={dim} data={d} turns={data.turns} segments={data.segments ?? []} />
              ) : null;
            })}
          </div>
          <TrajectoryFootnote data={data} />
        </>
      )}
    </section>
  );
}

function TrajectoryChart({
  data,
  turns,
  segments,
}: {
  data: TrajectoryDim;
  turns: TurnMarker[];
  segments: SegmentBand[];
}) {
  const color = COLORS[data.dim] ?? "#7a6a9e";
  const primary = PRIMARY_DIMS.includes(data.dim);
  const subFlags = data.forecasts.flatMap((f) => f.subgroup_flags);
  const reducedConfidence = subFlags.length > 0;

  const option = useMemo<EChartsOption>(() => {
    const ttlLocal = data.time_to_limit;
    // continuous-lifecycle segment shading: alternate translucent bands per
    // lifecycle segment (observed history), so resets/turns read as steps
    const segAreas: echarts.MarkAreaComponentOption["data"] = [];
    segments.forEach((s, i) => {
      if (s.start_ts == null || s.end_ts == null) return;
      segAreas.push([
        { xAxis: s.start_ts, itemStyle: { color: i % 2 === 0 ? "rgba(122, 106, 158, 0.05)" : "rgba(122, 106, 158, 0.10)" } },
        { xAxis: s.end_ts },
      ]);
    });
    const limitLine = ttlLocal?.limit_mm != null
      ? {
          silent: true,
          symbol: "none" as const,
          lineStyle: { color: "#a13d34", width: 1, type: "dashed" as const },
          label: {
            formatter: () => `limit ${ttlLocal!.limit_mm} mm (${ttlLocal!.label ?? "approved"})`,
            position: "insideEndTop" as const,
            color: "#a13d34",
            fontSize: 9,
          },
          data: [{ yAxis: ttlLocal!.limit_mm }],
        }
      : undefined;
    const obsX: string[] = [];
    const obsY: (number | null)[] = [];
    for (const o of data.observed) {
      obsX.push(o.ts);
      obsY.push(o.value);
    }

    // forecast continuation from anchor through H horizons
    const fcX: string[] = [];
    const fcY: (number | null)[] = [];
    const lowY: (number | null)[] = [];
    const highY: (number | null)[] = [];
    const lastObs = obsX.length ? obsX[obsX.length - 1] : null;
    for (const f of data.forecasts) {
      fcX.push(f.asof_ts ?? lastObs ?? f.dim);
      fcY.push(f.predicted);
      lowY.push(f.low);
      highY.push(f.high);
    }
    // connector point = anchor value at as-of time
    const anchorX = lastObs;
    const anchorY = data.forecasts[0]?.current ?? null;
    const connX = anchorX != null ? [anchorX, ...fcX] : fcX;
    const connY = anchorY != null ? [anchorY, ...fcY] : fcY;

    // realised residual strip (actual vs forecast, historical asof)
    const resX: string[] = [];
    const resY: (number | null)[] = [];
    for (const r of data.realised) {
      if (r.ts && r.actual != null) {
        resX.push(r.ts);
        resY.push(r.actual);
      }
    }

    // conformal band (low..high): stacked high/low lines draw the fill
    const fcX2 = fcX.slice(); // forecast x positions (post-anchor)
    const highData: [string, number | null][] = fcX2.map((x, i) => [x, highY[i]]);
    const lowData: [string, number | null][] = fcX2.map((x, i) => [x, lowY[i]]);

    // lifecycle step markers: vertical reset lines at each confirmed turn
    const markLines: echarts.MarkLineComponentOption["data"] = [];
    // invisible scatter carrying the turn tooltip (markLine items can't carry one)
    const turnInfo: { ts: string; no: number; pre: number | null; post: number | null;
      dia_cut: number | null; days: number | null }[] = [];
    // anchor divider — visual separation between observed (solid) and forecast (dashed)
    if (anchorX != null) {
      markLines.push({
        xAxis: anchorX,
        label: {
          formatter: () => "anchor",
          position: "insideEndTop",
          color: "#82838c",
          fontSize: 9,
        },
        lineStyle: { color: "#f5a623", width: 1.6, type: "solid" },
      });
    }
    const turnScatter: [string, number][] = [];
    for (const t of turns) {
      const ts = t.post_ts ?? t.pre_ts;
      if (!ts) continue;
      const preVal = PRE_VAL[data.dim]?.(t);
      const postVal = data.dim === "wsmDia"
        ? t.post_wsmDia
        : data.dim === "wsmFlange"
          ? t.post_wsmFlange
          : data.dim === "wsmRoot"
            ? t.post_wsmRoot
            : t.post_wsmThread;
      markLines.push({
        xAxis: ts,
        label: {
          formatter: () => `turn ${t.turn_no}`,
          position: "insideStartTop",
          color: "#9a6700",
          fontSize: 9,
        },
        lineStyle: { color: "#d9a13b", width: 1.2, type: "dashed" },
      });
      // place an invisible point at a chart-visible y so axis-trigger tooltip fires
      const y = postVal ?? preVal ?? (data.observed.length ? data.observed[data.observed.length - 1].value : 0);
      if (y != null && Number.isFinite(y)) {
        turnScatter.push([ts, y]);
        turnInfo.push({ ts, no: t.turn_no, pre: preVal, post: postVal,
          dia_cut: t.dia_cut, days: t.days_between });
      }
    }

    const series: echarts.SeriesOption[] = [
      {
        name: "80% band (high)",
        type: "line",
        data: highData,
        stack: "conformal",
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color: BAND_COLOR },
        silent: true,
        tooltip: { show: false },
        z: 1,
      },
      {
        name: "80% band (low)",
        type: "line",
        data: lowData,
        stack: "conformal",
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        silent: true,
        tooltip: { show: false },
        z: 1,
      },
      {
        name: `${data.dim} observed`,
        type: "line",
        data: obsX.map((x, i) => [x, obsY[i]]),
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { color, width: 1.6 },
        itemStyle: { color },
        connectNulls: false,
        showSymbol: data.observed.length <= 40,
        z: 2,
        markLine: limitLine,
        markArea: segAreas.length ? { silent: true, data: segAreas, z: 0 } : undefined,
        tooltip: { valueFormatter: (v) => `${fmt(v as number)} mm` },
      },
      {
        name: "forecast (anchor + Δ)",
        type: "line",
        data: connX.map((x, i) => [x, connY[i]]),
        symbol: reducedConfidence ? "diamond" : "circle",
        symbolSize: reducedConfidence ? 7 : 5,
        lineStyle: reducedConfidence
          ? { color: "#d9a13b", width: 1.8, type: "dotted" }
          : { color, width: 1.8, type: "dashed" },
        itemStyle: reducedConfidence ? { color: "#d9a13b" } : { color },
        connectNulls: true,
        z: 3,
        markLine: { silent: true, data: markLines },
        tooltip: { valueFormatter: (v) => `${fmt(v as number)} mm` },
      },
    ];

    if (resX.length) {
      series.push({
        name: "realised",
        type: "scatter",
        data: resX.map((x, i) => [x, resY[i]]),
        symbol: "triangle",
        symbolSize: 9,
        itemStyle: { color: "#14151a", borderColor: "#fff", borderWidth: 1 },
        z: 4,
        tooltip: { valueFormatter: (v) => `${fmt(v as number)} mm` },
      });
    }

    if (turnScatter.length) {
      series.push({
        name: "turn",
        type: "scatter",
        data: turnScatter,
        symbol: "none",
        silent: false,
        z: 5,
        tooltip: {
          trigger: "item",
          formatter: (p) => {
            const info = turnInfo[p.dataIndex];
            if (!info) return "";
            return (
              `<b>Turn ${info.no}</b> · ${info.ts.slice(0, 10)}` +
              `<br/>pre ${data.dim} = ${info.pre != null ? fmt(info.pre, 3) : "—"} mm` +
              `<br/>post ${data.dim} = ${info.post != null ? fmt(info.post, 3) : "—"} mm` +
              (info.dia_cut != null ? `<br/>dia cut = ${fmt(info.dia_cut, 1)} mm` : "") +
              (info.days != null ? `<br/>days between = ${fmt(info.days, 0)}` : "")
            );
          },
        },
      });
    }

    return {
      animation: false,
      grid: { left: 46, right: 16, top: 28, bottom: 42 },
      title: {
        text: data.dim,
        left: 0,
        top: 0,
        textStyle: { fontSize: 13, color: "#14151a", fontWeight: 600 },
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        valueFormatter: (v: unknown) => `${fmt(v)} mm`,
      },
      legend: {
        bottom: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { fontSize: 10, color: "#82838c" },
        data: data.forecasts.length ? ["forecast (anchor + Δ)", "realised"] : ["realised"],
      },
      xAxis: {
        type: "time",
        axisLabel: { fontSize: 10, color: "#a7a8b0" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { fontSize: 10, color: "#a7a8b0" },
        splitLine: { lineStyle: { color: "#f0f0e9" } },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 12, bottom: 18 }],
      series,
    };
  }, [data, turns, reducedConfidence, color]);

  const residualOption = useMemo<EChartsOption>(() => {
    const points = data.realised
      .filter((r) => r.ts != null && r.residual != null)
      .map((r) => [r.ts as string, r.residual as number]);
    return {
      animation: false,
      grid: { left: 46, right: 16, top: 22, bottom: 24 },
      title: { text: "realised residual (actual − forecast)", left: 0, top: 0,
        textStyle: { fontSize: 10, color: "#82838c", fontWeight: 500 } },
      tooltip: { trigger: "axis", confine: true,
        valueFormatter: (v: unknown) => `${fmt(v)} mm` },
      xAxis: { type: "time", axisLabel: { fontSize: 9, color: "#a7a8b0" }, splitLine: { show: false } },
      yAxis: { type: "value", axisLabel: { fontSize: 9, color: "#a7a8b0" }, splitLine: { lineStyle: { color: "#f0f0e9" } } },
      series: [{ name: "residual", type: "line", data: points, symbol: "circle", symbolSize: 5,
        lineStyle: { color: "#14151a", width: 1 }, itemStyle: { color: "#14151a" }, connectNulls: false,
        markLine: { silent: true, symbol: "none", lineStyle: { color: "#b8b8b0", width: 1, type: "dashed" }, data: [{ yAxis: 0 }] } }],
    };
  }, [data.realised]);

  const flags = data.flags;
  const nf = data.noise_floor_mm;
  const flagGroups = Array.from(new Set(subFlags.map((s) => s.group))).join(", ");
  const ttl = data.time_to_limit;
  const adapted = data.forecasts.filter(
    (f) => f.wheel_adaptation?.applied && f.wheel_adaptation?.bias_mm != null,
  );

  return (
    <div className="trajectory-card">
      <EChart option={option} height={260} />
      {data.realised.some((r) => r.ts != null && r.residual != null) && (
        <div className="residual-strip">
          <EChart option={residualOption} height={92} />
          <span className="muted tiny residual-note">positive = actual wear above forecast · negative = below forecast</span>
        </div>
      )}
      <div className="trajectory-meta">
        {reducedConfidence && (
          <span
            className="flag flag-reduced"
            title={subFlags
              .map(
                (s) =>
                  `${s.group}:${s.level} · ${s.reason} (n=${s.n}, bias=${fmt(
                    s.bias_mm,
                    3,
                  )} mm, cov=${s.coverage != null ? fmt(s.coverage, 2) : "—"})`,
              )
              .join("\n")}
          >
            ⚠ reduced confidence — {flagGroups}
          </span>
        )}
        {adapted.length > 0 && (
          <span
            className="flag flag-adapted"
            title={adapted
              .map(
                (f) =>
                  `${f.horizon} d: +${fmt(f.wheel_adaptation!.bias_mm!, 3)} mm (prior n=${f.wheel_adaptation!.prior_n})`,
              )
              .join("\n")}
          >
            adjusted for this wheel&apos;s recent behaviour
          </span>
        )}
        {ttl && (
          <span
            className={`chip${reducedConfidence ? " chip-reduced" : ""}`}
            title={ttl.note ?? ""}
          >
            {ttl.label}: {ttl.days_to_limit_point != null ? (
              <>
                {ttl.days_to_limit_point.toFixed(0)} d
                {ttl.days_to_limit_lo != null && (
                  <>
                    {" "}
                    <span className="muted">(band {ttl.days_to_limit_lo.toFixed(0)}–
                    {ttl.days_to_limit_hi != null ? ttl.days_to_limit_hi.toFixed(0) : "∞"} d)</span>
                  </>
                )}
              </>
            ) : (
              ">180 d"
            )}
          </span>
        )}
        {flags.length > 0 && (
          <span className="flag" title="Reported, never clipped">
            {flags.join(", ")}
          </span>
        )}
        {nf != null && (
          <span className="muted small">noise floor ≈ {nf.toFixed(3)} mm</span>
        )}
        {!primary && (
          <span className="muted small">derived diagnostic</span>
        )}
      </div>
    </div>
  );
}

const DIM_LABELS: Record<string, string> = {
  wsmFlange: "Flange",
  wsmRoot: "Root",
  wsmThread: "Thread",
  wsmDia: "Dia",
};
const HORIZONS = [30, 90, 180] as const;

function halfWidth(f: TrajectoryForecast): number | null {
  if (f.high != null && f.low != null) return Math.abs(f.high - f.low) / 2;
  if (f.high != null && f.predicted != null) return Math.abs(f.high - f.predicted);
  if (f.low != null && f.predicted != null) return Math.abs(f.predicted - f.low);
  return null;
}

function ForecastReadout({
  data,
  showDia,
  reduced,
}: {
  data: TrajectoryContract;
  showDia: boolean;
  reduced: Set<string>;
}) {
  const dims = showDia ? data.dims : data.dims.filter((d) => d.dim !== "wsmDia");
  const withForecasts = dims.filter((d) => d.forecasts.length > 0);
  if (withForecasts.length === 0) return null;

  return (
    <div className="forecast-readout">
      <span className="fs-label">
        Expected state
        {data.monotone_enforced && (
          <span
            className="fs-cond"
            title="Path is constrained to a physically valid no-turn trajectory: wear never decreases and diameter never increases across the horizons."
          >
            no-turn conditional path
          </span>
        )}
      </span>
      {withForecasts.map((d) => {
        const byH: Record<number, TrajectoryForecast> = {};
        for (const f of d.forecasts) byH[f.horizon] = f;
        const conf = data.conformal?.[d.dim];
        return (
          <div className="fs-row" key={d.dim}>
            <span className="fs-dim" style={{ color: COLORS[d.dim] ?? "#7a6a9e" }}>
              {DIM_LABELS[d.dim] ?? d.dim}
            </span>
            <span className="fs-cells">
              {HORIZONS.map((h) => {
                const f = byH[h];
                if (!f || f.predicted == null) {
                  return (
                    <span className="fs-cell" key={h}>
                      <span className="fs-h">{h}d</span>
                      <span className="fs-na">—</span>
                    </span>
                  );
                }
                const hw = halfWidth(f);
                const band = conf?.[`${h}d`];
                const pctLevel = band?.level != null ? (band.level * 100).toFixed(0) : "80";
                const pctActual =
                  band?.coverage != null ? "· emp. " + (band.coverage * 100).toFixed(0) + "%" : "";
                const reducedHere = reduced.has(d.dim);
                return (
                  <span className="fs-cell" key={h}>
                    <span className="fs-h">{h}d</span>
                    <b>{fmt(f.predicted, 3)}</b>
                    {hw != null && <span className="fs-range"> ± {fmt(hw, 3)} mm</span>}
                    <span
                      className={`fs-band${reducedHere ? " fs-band-reduced" : ""}`}
                      title={
                        band?.coverage != null
                          ? `Split-conformal ${pctLevel}% interval; empirical test coverage ${(
                              band.coverage * 100
                            ).toFixed(1)}%`
                          : `Split-conformal ${pctLevel}% interval`
                      }
                    >
                      ({pctLevel}%{pctActual}
                      {reducedHere ? " ⚠" : ""})
                    </span>
                  </span>
                );
              })}
            </span>
          </div>
        );
      })}
      <p className="muted small fs-note">
        Same delta forecasts as the charts. "No-turn conditional": the path assumes no
        turning/replacement inside the horizon, so wear can only hold or grow (diameter only
        hold or shrink) across 30/90/180 d. The ± is the half-width of the split-conformal
        band (nominal 80%); the number in brackets is the band level plus empirical test
        coverage, so "small ± / high %" is trustworthy and "large ± / low %" means the
        horizon range is wide. Diameter is a derived diagnostic, not a decision input.
      </p>
    </div>
  );
}

function TrajectoryFootnote({ data }: { data: TrajectoryContract }) {
  const m = data.model;
  const mor = m?.model_of_record;
  const morLabel = mor
    ? Object.entries(mor)
        .map(([dim, src]) => `${dim}:${src === "wear_rate" ? "rate" : "Δhor"}`)
        .join(" ")
    : null;
  return (
    <p className="muted small trajectory-footnote">
      Forecast = anchor + Δ from serving C1 models (train cutoff{" "}
      {m?.train_cutoff ?? "—"}, n={m?.n_train?.toLocaleString() ?? "—"});
      {morLabel ? <span> model of record {morLabel};</span> : null} the path is
      no-turn conditional and monotone — wear can only hold or grow, diameter only hold or
      shrink across 30/90/180 d — enforced after wheelset adaptation; 80%
      split-conformal bands + noise floor from the trajectory artefact;       realised
      points are actual within-segment measurements when a historical as-of is
      chosen. Physics flags (wear improving / diameter increasing) are reported,
      never clipped. Diameter is derived and never the primary trajectory.
      "Days to condemning" is the first piecewise-linear crossing of a Wrpld
      condemning limit (dia 1016 mm hard stop, flange 3.0 / root 6.0 / tread 6.5
      mm wear — register `ml/configs/limit_register_v1.json`, approved 2026-08-19);
      the band uses the conformal interval edges. The three-step action ladder
      beyond condemning is a policy layer, separate from the approved limits.
      Amber dashed vertical lines mark confirmed turning events (reset steps);
      the yellow line is the anchor (observed → forecast split). Amber
      "reduced confidence" marks a wheelset that belongs to a collapsed
      subgroup (shed / wear band) for that dimension — the point forecast is
      shown but not decision-grade there. A "restored" banner marks an anchor
      that is itself a lifecycle boundary: the forecast continues from the
      post-turn/post-replacement level rather than extrapolating the reset as
      continuous wear. "Adjusted" forecasts are shifted by the wheelset&apos;s
      recent same-segment bias (prior measurements of this wheel) before the
      80% band is drawn.
    </p>
  );
}
