import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { api } from "./api";
import type { TrajectoryContract, TrajectoryDim } from "./types";

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

export function TrajectoryPanel({ wheelsetId }: { wheelsetId: number }) {
  const [data, setData] = useState<TrajectoryContract | null>(null);
  const [asof, setAsof] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setErr(null);
    setData(null);
    api
      .trajectory(wheelsetId, asof || undefined)
      .then(setData)
      .catch((e) => setErr((e as Error).message))
      .finally(() => setLoading(false));
  }, [wheelsetId, asof]);

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

      {err && <div className="error">{err}</div>}
      {loading && <p className="muted">loading…</p>}

      {data && (
        <>
          <div className="trajectory-grid">
            {dimOrder.map((dim) => {
              const d = data.dims.find((x) => x.dim === dim);
              return d ? (
                <TrajectoryChart key={dim} data={d} />
              ) : null;
            })}
          </div>
          <TrajectoryFootnote data={data} />
        </>
      )}
    </section>
  );
}

function TrajectoryChart({ data }: { data: TrajectoryDim }) {
  const ref = useRef<HTMLDivElement>(null);
  const color = COLORS[data.dim] ?? "#2563eb";
  const primary = PRIMARY_DIMS.includes(data.dim);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);

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
        symbol: "diamond",
        symbolSize: 7,
        lineStyle: { color, width: 1.8, type: "dashed" },
        itemStyle: { color },
        connectNulls: true,
        z: 3,
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

    chart.setOption({
      animation: false,
      grid: { left: 46, right: 16, top: 28, bottom: 42 },
      title: {
        text: data.dim,
        left: 0,
        top: 0,
        textStyle: { fontSize: 13, color: "#1f2333", fontWeight: 600 },
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
        textStyle: { fontSize: 10, color: "#6b7280" },
        data: ["forecast (anchor + Δ)", "realised"],
      },
      xAxis: {
        type: "time",
        axisLabel: { fontSize: 10, color: "#888" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { fontSize: 10, color: "#888" },
        splitLine: { lineStyle: { color: "#f0f0f0" } },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 12, bottom: 18 }],
      series,
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  const flags = data.flags;
  const nf = data.noise_floor_mm;

  return (
    <div className="trajectory-card">
      <div ref={ref} className="trajectory-chart" />
      <div className="trajectory-meta">
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
      split-conformal bands + noise floor from the trajectory artefact; realised
      points are actual within-segment measurements when a historical as-of is
      chosen. Physics flags (wear improving / diameter increasing) are reported,
      never clipped. Diameter is derived and never the primary trajectory.
    </p>
  );
}
