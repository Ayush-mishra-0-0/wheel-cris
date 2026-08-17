import { useEffect, useRef, useState } from "react";
import type { ECharts, EChartsCoreOption } from "echarts";

export type EChartsOption = EChartsCoreOption;

// echarts is the largest dependency; dynamic-import it once so it becomes its
// own chunk instead of inflating the main bundle. Every chart goes through
// this single wrapper, so the async load happens here and nowhere else.
let echartsPromise: Promise<typeof import("echarts")> | null = null;
function loadECharts(): Promise<typeof import("echarts")> {
  if (!echartsPromise) echartsPromise = import("echarts");
  return echartsPromise;
}

/** Thin ECharts React wrapper: init/resize/dispose lifecycle only.
 *  Charts stay data-agnostic — they pass a pure option object; if ECharts is
 *  ever swapped, only this file changes. Init is async (echarts is
 *  code-split), so setOption/events run once the instance is ready. */
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
  const chartRef = useRef<ECharts | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    let disposed = false;
    let chart: ECharts | null = null;
    const onResize = () => chart?.resize();
    loadECharts()
      .then((m) => {
        if (disposed || !ref.current) return;
        chart = m.init(ref.current);
        chartRef.current = chart;
        window.addEventListener("resize", onResize);
        setReady(true);
      })
      .catch(() => {}); // echarts failed to load; charts stay blank
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      chart?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (ready && chartRef.current) chartRef.current.setOption(option, true);
  }, [option, ready]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!ready || !chart || !onEvents) return;
    const bindings = Object.entries(onEvents).map(([name, fn]) => {
      chart.on(name, fn);
      return name;
    });
    return () => bindings.forEach((n) => chart.off(n));
  }, [onEvents, ready]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}