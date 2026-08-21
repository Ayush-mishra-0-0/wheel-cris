import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "./EChart";
import { EChart } from "./EChart";
import { api } from "./api";
import type { LocoWheelsetRow, TrajectoryContract, TrajectoryDim } from "./types";
import { LimitChip } from "./LimitChip";
import { SkeletonBlock } from "./States";

const PRIMARY_DIMS = ["wsmFlange", "wsmRoot", "wsmThread"];
const DERIVED_DIMS = ["wsmDia"];

// Okabe–Ito colour-blind-safe palette, assigned per wheelset in list order.
const WHEEL_COLORS = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#56B4E9", "#CC79A7"];

function fmt(v: unknown, d = 2): string {
  const n = typeof v === "number" ? v : Number(v);
  return !isFinite(n) ? "—" : n.toFixed(d);
}

export function OverlayPanel({
  wheelsets,
  onHover,
}: {
  wheelsets: LocoWheelsetRow[];
  onHover?: (ws: number | null) => void;
}) {
  // One loco comparison is six wheelsets; exclude extra historical rows from
  // the shared axis while keeping the selection client-side.
  const plottedWheelsets = useMemo(
    () => [...wheelsets]
      .sort((a, b) => (a.axle_position_1_6 ?? 99) - (b.axle_position_1_6 ?? 99)
        || (a.wheel_position_1_12 ?? 99) - (b.wheel_position_1_12 ?? 99)
        || a.wheelset_equipment_id - b.wheelset_equipment_id)
      .slice(0, 6),
    [wheelsets],
  );
  const ids = useMemo(() => plottedWheelsets.map((w) => w.wheelset_equipment_id), [plottedWheelsets]);
  const idKey = ids.join(",");

  const [checked, setChecked] = useState<Set<number>>(() => new Set(ids));
  const [data, setData] = useState<Record<number, TrajectoryContract | undefined>>({});
  const [asof, setAsof] = useState("");
  const [showDia, setShowDia] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const chartRefs = useRef<Map<string, echarts.ECharts>>(new Map());

  useEffect(() => {
    setChecked(new Set(ids));
  }, [idKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setLoading(true);
    setErr(null);
    setData({});
    chartRefs.current.clear();
    let cancelled = false;
    (async () => {
      const entries = await Promise.all(
        ids.map(async (id) => {
          try {
            const c = await api.trajectory(id, asof || undefined);
            return [id, c] as const;
          } catch {
            return [id, undefined] as const;
          }
        }),
      );
      if (cancelled) return;
      setData(Object.fromEntries(entries));
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [idKey, asof]);

  const colorById = useMemo(() => {
    const m: Record<number, string> = {};
    plottedWheelsets.forEach((w, i) => {
      m[w.wheelset_equipment_id] = WHEEL_COLORS[i % WHEEL_COLORS.length];
    });
    return m;
  }, [plottedWheelsets]);

  const visible = plottedWheelsets.filter((w) => checked.has(w.wheelset_equipment_id));
  const dims = showDia ? [...PRIMARY_DIMS, ...DERIVED_DIMS] : [...PRIMARY_DIMS];
  const anyVisible = visible.length > 0;

  const toggle = (id: number) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allChecked = visible.length === plottedWheelsets.length;

  const handleExport = async (format: "csv" | "png" | "svg") => {
    setExporting(format);
    try {
      if (format === "csv") {
        const lines = ["wheelset_id,dim,kind,ts,value_mm"];
        for (const w of visible) {
          const c = data[w.wheelset_equipment_id];
          if (!c) continue;
          for (const d of c.dims) {
            if (!showDia && d.dim === "wsmDia") continue;
            for (const o of d.observed) {
              lines.push(`${w.wheelset_equipment_id},${d.dim},observed,${o.ts},${o.value ?? ""}`);
            }
            for (const f of d.forecasts) {
              lines.push(
                `${w.wheelset_equipment_id},${d.dim},forecast,${f.asof_ts ?? ""},${f.predicted ?? ""}`,
              );
            }
            for (const r of d.realised) {
              if (r.ts && r.actual != null) {
                lines.push(`${w.wheelset_equipment_id},${d.dim},realised,${r.ts},${r.actual}`);
              }
            }
          }
        }
        downloadBlob(lines.join("\n"), "text/csv", `wheelset_overlay_${idKey.split(",").join("_")}_${asof || "latest"}.csv`);
      } else {
        // one file per dim chart, captured from its live echarts instance
        for (const dim of dims) {
          const chart = chartRefs.current.get(dim);
          if (!chart) continue;
          const url = chart.getDataURL({ type: format, pixelRatio: 2, backgroundColor: "#ffffff" });
          const a = document.createElement("a");
          a.href = url;
          a.download = `wheelset_overlay_${dim}_${asof || "latest"}.${format}`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setExporting(null);
    }
  };

  return (
    <section className="trajectory overlay">
      <div className="asof overlay-asof">
        <label>
          As-of (historical re-anchor shows residual strip):
          <input type="date" value={asof} onChange={(e) => setAsof(e.target.value)} />
          {asof && (
            <button className="clear" onClick={() => setAsof("")}>
              latest
            </button>
          )}
        </label>
      </div>

      <div className="overlay-picks">
        <button
          className="chip pick-all"
          onClick={() => setChecked(new Set(ids))}
          title="Show all wheelsets"
        >
          {allChecked ? "✓ all" : "select all"}
        </button>
        <button className="chip pick-none" onClick={() => setChecked(new Set())}>
          clear
        </button>
        {plottedWheelsets.map((w) => {
          const id = w.wheelset_equipment_id;
          const on = checked.has(id);
          return (
            <label
              key={id}
              className={`overlay-pick${on ? " on" : ""}`}
              style={{ "--wc": colorById[id] } as CSSProperties}
            >
              <input
                type="checkbox"
                checked={on}
                onChange={() => toggle(id)}
                onMouseEnter={() => onHover?.(id)}
                onMouseLeave={() => onHover?.(null)}
              />
              <span className="overlay-swatch" />
              <span className="mono">#{id}</span>
              {w.wheel_position_1_12 != null && (
                <span className="muted small">pos {fmt(w.wheel_position_1_12, 0)}</span>
              )}
              {w.limiting_dim && <LimitChip dim={w.limiting_dim} />}
              {w.pturn_90d_calibrated != null && (
                <span className={`mono small ${w.pturn_90d_calibrated >= 0.05 ? "risk-high" : w.pturn_90d_calibrated >= 0.01 ? "risk-mid" : "risk-low"}`} title={`calibrated ${(w.pturn_90d_calibrated*100).toFixed(1)}% (raw ${(w.pturn_90d ?? 0 *100).toFixed(1)}%)`}>
                  {(w.pturn_90d_calibrated*100).toFixed(1)}%
                </span>
              )}
            </label>
          );
        })}
      </div>

      <div className="export-buttons">
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
        <span className="dim-toggle-spacer" />
        <label className="muted small">Export:</label>
        <button onClick={() => handleExport("csv")} disabled={exporting !== null || loading || !anyVisible} className="export-btn">
          {exporting === "csv" ? "…" : "CSV"}
        </button>
        <button onClick={() => handleExport("png")} disabled={exporting !== null || loading || !anyVisible} className="export-btn">
          {exporting === "png" ? "…" : "PNG"}
        </button>
        <button onClick={() => handleExport("svg")} disabled={exporting !== null || loading || !anyVisible} className="export-btn">
          {exporting === "svg" ? "…" : "SVG"}
        </button>
      </div>

      {err && <div className="error">{err}</div>}
      {!loading && !anyVisible && (
        <div className="empty-state">
          <div className="empty-title">No wheelsets selected</div>
          <p className="muted small">Pick at least one wheelset to draw its wear paths.</p>
        </div>
      )}
      {loading && <SkeletonBlock lines={5} />}

      {!loading && anyVisible && (
        <div className="trajectory-grid">
          {dims.map((dim) => {
            const entries = visible
              .map((w) => ({
                w,
                color: colorById[w.wheelset_equipment_id],
                d: data[w.wheelset_equipment_id]?.dims.find((x) => x.dim === dim),
              }))
              .filter((e) => e.d);
            if (entries.length === 0) return null;
            const limitMm = entries
              .map((e) => e.d!.time_to_limit?.limit_mm)
              .find((v) => v != null);
            return (
              <OverlayChart
                key={dim}
                dimKey={dim}
                entries={entries.map((e) => ({ id: e.w.wheelset_equipment_id, color: e.color, d: e.d! }))}
                limitMm={limitMm ?? undefined}
                onHover={onHover}
                onInstance={(chart) => {
                  chartRefs.current.set(dim, chart);
                }}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function downloadBlob(text: string, mime: string, filename: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function OverlayChart({
  dimKey,
  entries,
  limitMm,
  onHover,
  onInstance,
}: {
  dimKey: string;
  entries: { id: number; color: string; d: TrajectoryDim }[];
  limitMm?: number;
  onHover?: (ws: number | null) => void;
  onInstance?: (chart: echarts.ECharts) => void;
}) {
  const option = useMemo<EChartsOption>(() => {
    const series: echarts.SeriesOption[] = [];
    const legendData: string[] = [];

    for (const e of entries) {
      const label = `#${e.id}`;
      const reduced = e.d.forecasts.some((f) => (f.subgroup_flags ?? []).length > 0);
      legendData.push(label);
      series.push({
        name: label,
        type: "line",
        data: e.d.observed.map((o) => [o.ts, o.value]),
        symbol: "circle",
        symbolSize: 3,
        lineStyle: { color: e.color, width: 1.5 },
        itemStyle: { color: e.color },
        // Missing wheelset measurements are real gaps; do not interpolate them.
        connectNulls: false,
        showSymbol: e.d.observed.length <= 60,
        markLine:
          limitMm != null
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#a13d34", width: 1, type: "dashed" },
                label: {
                  formatter: () => `limit ${limitMm} mm`,
                  position: "insideEndTop",
                  color: "#a13d34",
                  fontSize: 9,
                },
                data: [{ yAxis: limitMm }],
              }
            : undefined,
        tooltip: { valueFormatter: (v: unknown) => `${fmt(v)} mm` },
      });
      // forecast continuation from anchor through H horizons
      const lastObs = e.d.observed.length ? e.d.observed[e.d.observed.length - 1].ts : null;
      const fcX: string[] = [];
      const fcY: (number | null)[] = [];
      const connX: string[] = [];
      const connY: (number | null)[] = [];
      for (const f of e.d.forecasts) {
        fcX.push(f.asof_ts ?? lastObs ?? f.dim);
        fcY.push(f.predicted);
      }
      if (fcX.length) {
        const anchorX = lastObs;
        const anchorY = e.d.forecasts[0]?.current ?? null;
        if (anchorX != null) connX.push(anchorX);
        if (anchorY != null) connY.push(anchorY);
        connX.push(...fcX);
        connY.push(...fcY);
        series.push({
          name: label,
          type: "line",
          data: connX.map((x, i) => [x, connY[i]]),
          symbol: reduced ? "diamond" : "circle",
          symbolSize: reduced ? 5 : 3,
          lineStyle: reduced
            ? { color: e.color, width: 1.6, type: "dotted" }
            : { color: e.color, width: 1.8, type: "dashed" },
          itemStyle: { color: e.color },
          connectNulls: false,
          tooltip: { valueFormatter: (v: unknown) => `${fmt(v)} mm` },
        });
      }
    }

    return {
      animation: false,
      grid: { left: 46, right: 16, top: 28, bottom: 42 },
      title: {
        text: dimKey,
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
        data: legendData,
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
  }, [entries, limitMm, dimKey]);

  return (
    <div className="trajectory-card">
      <EChart
        option={option}
        height={260}
        onInstance={onInstance}
        onEvents={{
          mouseover: (p) => {
            const name = (p as { seriesName?: string })?.seriesName;
            if (name && name.startsWith("#")) {
              onHover?.(Number(name.slice(1)));
            }
          },
          globalout: () => onHover?.(null),
        }}
      />
    </div>
  );
}
