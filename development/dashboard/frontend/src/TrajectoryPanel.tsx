import { useEffect, useMemo, useState } from "react";
import * as echarts from "echarts";
import { EChart } from "./EChart";
import type { EChartsOption } from "./EChart";
import { api } from "./api";
import type { TrajectoryContract, TrajectoryDim, TurnMarker } from "./types";
import { ErrorState, SkeletonBlock } from "./States";

const PRIMARY_DIMS = ["wsmFlange", "wsmRoot", "wsmThread"];
const DERIVED_DIMS = ["wsmDia"];
const COLORS: Record<string, string> = {
  wsmFlange: "#e74c3c",
  wsmRoot: "#8e44ad",
  wsmThread: "#27ae60",
  wsmDia: "#1f77b4",
};
const BAND_COLOR = "rgba(37, 99, 235, 0.10)";

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

  const dimOrder = [...PRIMARY_DIMS, ...DERIVED_DIMS];

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

      {err && !loading && <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />}
      {loading && <SkeletonBlock lines={5} />}

      {data && (
        <>
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
          <div className="trajectory-grid">
            {dimOrder.map((dim) => {
              const d = data.dims.find((x) => x.dim === dim);
              return d ? (
                <TrajectoryChart key={dim} data={d} turns={data.turns} />
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
}: {
  data: TrajectoryDim;
  turns: TurnMarker[];
}) {
  const color = COLORS[data.dim] ?? "#2563eb";
  const primary = PRIMARY_DIMS.includes(data.dim);
  const subFlags = data.forecasts.flatMap((f) => f.subgroup_flags);
  const reducedConfidence = subFlags.length > 0;

  const option = useMemo<EChartsOption>(() => {
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
          color: "#4f46e5",
          fontSize: 9,
        },
        lineStyle: { color: "#4f46e5", width: 1.4, type: "solid" },
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
          color: "#b45309",
          fontSize: 9,
        },
        lineStyle: { color: "#d97706", width: 1.2, type: "dashed" },
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
        tooltip: { valueFormatter: (v) => `${fmt(v as number)} mm` },
      },
      {
        name: "forecast (anchor + Δ)",
        type: "line",
        data: connX.map((x, i) => [x, connY[i]]),
        symbol: reducedConfidence ? "diamond" : "circle",
        symbolSize: reducedConfidence ? 7 : 5,
        lineStyle: reducedConfidence
          ? { color: "#d97706", width: 1.8, type: "dotted" }
          : { color, width: 1.8, type: "dashed" },
        itemStyle: reducedConfidence ? { color: "#d97706" } : { color },
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
        itemStyle: { color: "#111827", borderColor: "#fff", borderWidth: 1 },
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
        textStyle: { fontSize: 13, color: "#1c1917", fontWeight: 600 },
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
        textStyle: { fontSize: 10, color: "#78716c" },
        data: ["forecast (anchor + Δ)", "realised"],
      },
      xAxis: {
        type: "time",
        axisLabel: { fontSize: 10, color: "#a8a29e" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { fontSize: 10, color: "#a8a29e" },
        splitLine: { lineStyle: { color: "#f5f5f4" } },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 12, bottom: 18 }],
      series,
    };
  }, [data, turns, reducedConfidence, color]);

  const flags = data.flags;
  const nf = data.noise_floor_mm;
  const flagGroups = Array.from(new Set(subFlags.map((s) => s.group))).join(", ");
  const ttl = data.time_to_limit;

  return (
    <div className="trajectory-card">
      <EChart option={option} height={260} />
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

function TrajectoryFootnote({ data }: { data: TrajectoryContract }) {
  const m = data.model;
  return (
    <p className="muted small trajectory-footnote">
      Forecast = anchor + Δ from serving C1 models (train cutoff{" "}
      {m?.train_cutoff ?? "—"}, n={m?.n_train?.toLocaleString() ?? "—"}); 80%
      split-conformal bands + noise floor from the trajectory artefact;       realised
      points are actual within-segment measurements when a historical as-of is
      chosen. Physics flags (wear improving / diameter increasing) are reported,
      never clipped. Diameter is derived and never the primary trajectory.
      "Days to condemning" is the first piecewise-linear crossing of the 1016 mm
      dia hard stop (the only approved limit); the band uses the conformal
      interval edges. Flange/root/tread action thresholds are not yet approved.
      Amber dashed vertical lines mark confirmed turning events (reset steps);
      the indigo line is the anchor (observed → forecast split). Amber
      "reduced confidence" marks a wheelset that belongs to a collapsed
      subgroup (shed / wear band) for that dimension — the point forecast is
      shown but not decision-grade there.
    </p>
  );
}
