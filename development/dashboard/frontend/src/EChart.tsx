import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export type EChartsOption = echarts.EChartsCoreOption;

/** Thin ECharts React wrapper: init/resize/dispose lifecycle only.
 *  Charts stay data-agnostic — they pass a pure option object; if ECharts is
 *  ever swapped, only this file changes. */
export function EChart({
  option,
  height = 260,
  onEvents,
}: {
  option: EChartsOption;
  height?: number | string;
  onEvents?: Record<string, (params: unknown) => void>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (chartRef.current) chartRef.current.setOption(option, true);
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onEvents) return;
    const bindings = Object.entries(onEvents).map(([name, fn]) => {
      chart.on(name, fn);
      return name;
    });
    return () => bindings.forEach((n) => chart.off(n));
  }, [onEvents]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
