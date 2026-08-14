import { useMemo } from "react";
import type { MeasurementPoint } from "./types";
import { EChart, type EChartsOption } from "./EChart";

const WEAR = [
  { key: "wsmFlange", label: "flange", color: "#e74c3c", get: (m: MeasurementPoint) => m.mean_wsmFlange },
  { key: "wsmThread", label: "tread", color: "#27ae60", get: (m: MeasurementPoint) => m.mean_wsmThread },
  { key: "wsmRoot", label: "root", color: "#8e44ad", get: (m: MeasurementPoint) => m.mean_wsmRoot },
];
const DIA_COLOR = "#1f77b4";

export function WearTimeline({ measurements }: { measurements: MeasurementPoint[] }) {
  const option = useMemo<EChartsOption>(() => {
    const times = measurements.map((m) => m.measurement_timestamp);

    const wearSeries = WEAR.map((s) => ({
      name: s.label,
      type: "line" as const,
      yAxisIndex: 0,
      data: measurements.map((m, i) => [times[i], s.get(m)] as [string, number | null]),
      symbol: "circle",
      symbolSize: 3,
      showSymbol: measurements.length <= 60,
      lineStyle: { color: s.color, width: 1.7 },
      itemStyle: { color: s.color },
      connectNulls: false,
      tooltip: { valueFormatter: (v: unknown) => `${typeof v === "number" ? v.toFixed(3) : "—"} mm` },
    }));

    const diaSeries = {
      name: "dia",
      type: "line" as const,
      yAxisIndex: 1,
      data: measurements.map((m, i) => [times[i], m.mean_wsmDia] as [string, number | null]),
      symbol: "circle",
      symbolSize: 3,
      showSymbol: measurements.length <= 60,
      lineStyle: { color: DIA_COLOR, width: 1.7, opacity: 0.85 },
      itemStyle: { color: DIA_COLOR },
      connectNulls: false,
      tooltip: { valueFormatter: (v: unknown) => `${typeof v === "number" ? v.toFixed(1) : "—"} mm` },
    };

    const turnData: [string, number][] = [];
    const turnInfo: { ts: string; flange: number | null; root: number | null; tread: number | null; dia: number | null }[] = [];
    for (const m of measurements) {
      if (!m.turn_event) continue;
      turnData.push([m.measurement_timestamp, m.mean_wsmFlange ?? m.mean_wsmRoot ?? 0]);
      turnInfo.push({
        ts: m.measurement_timestamp,
        flange: m.mean_wsmFlange,
        root: m.mean_wsmRoot,
        tread: m.mean_wsmThread,
        dia: m.mean_wsmDia,
      });
    }

    return {
      animation: false,
      grid: { left: 48, right: 52, top: 30, bottom: 42 },
      legend: {
        bottom: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { fontSize: 11, color: "#78716c" },
      },
      tooltip: {
        trigger: "axis",
        confine: true,
      },
      xAxis: {
        type: "time",
        axisLabel: { fontSize: 10, color: "#a8a29e" },
        splitLine: { show: false },
      },
      yAxis: [
        {
          type: "value",
          name: "wear (mm)",
          scale: true,
          nameTextStyle: { fontSize: 10, color: "#a8a29e" },
          axisLabel: { fontSize: 10, color: "#a8a29e" },
          splitLine: { lineStyle: { color: "#f5f5f4" } },
        },
        {
          type: "value",
          name: "dia (mm)",
          scale: true,
          nameTextStyle: { fontSize: 10, color: DIA_COLOR },
          axisLabel: { fontSize: 10, color: DIA_COLOR },
          splitLine: { show: false },
        },
      ],
      dataZoom: [{ type: "inside" }, { type: "slider", height: 12, bottom: 18 }],
      series: [
        ...wearSeries,
        diaSeries,
        {
          name: "turn",
          type: "scatter",
          data: turnData,
          symbol: "diamond",
          symbolSize: 9,
          itemStyle: { color: "#f59e0b", borderColor: "#fff", borderWidth: 1 },
          z: 5,
          tooltip: {
            trigger: "item",
            formatter: (p: unknown) => {
              const pp = p as { dataIndex: number };
              const m = turnInfo[pp.dataIndex];
              if (!m) return "";
              return (
                `<b>Turning event</b> · ${m.ts.slice(0, 10)}` +
                `<br/>flange ${m.flange ?? "—"} · root ${m.root ?? "—"}` +
                `<br/>tread ${m.tread ?? "—"} · dia ${m.dia ?? "—"} mm`
              );
            },
          },
        },
      ],
    };
  }, [measurements]);

  if (measurements.length === 0) return <p className="muted">No measurements</p>;

  return (
    <div className="timeline">
      <EChart option={option} height={250} />
    </div>
  );
}
