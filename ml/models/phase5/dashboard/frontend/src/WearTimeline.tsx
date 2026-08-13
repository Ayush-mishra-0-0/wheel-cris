import type { MeasurementPoint } from "./types";

const W = 760;
const H = 250;
const PAD = { l: 46, r: 46, t: 16, b: 26 };

const WEAR = [
  { key: "wsmFlange", color: "#e74c3c", get: (m: MeasurementPoint) => m.mean_wsmFlange },
  { key: "wsmThread", color: "#27ae60", get: (m: MeasurementPoint) => m.mean_wsmThread },
  { key: "wsmRoot", color: "#8e44ad", get: (m: MeasurementPoint) => m.mean_wsmRoot },
];

export function WearTimeline({ measurements }: { measurements: MeasurementPoint[] }) {
  if (measurements.length === 0) return <p className="muted">No measurements</p>;

  const t0 = new Date(measurements[0].measurement_timestamp).getTime();
  const t1 = new Date(measurements[measurements.length - 1].measurement_timestamp).getTime();
  const span = Math.max(t1 - t0, 1);

  const wearVals = measurements.flatMap((m) => WEAR.map((s) => s.get(m)).filter((v) => v != null));
  const wMin = Math.min(...wearVals) ?? 0;
  const wMax = Math.max(...wearVals) ?? 1;
  const wSpan = Math.max(wMax - wMin, 1e-6);
  const wPad = wSpan * 0.1 || 0.3;

  const diaVals = measurements.map((m) => m.mean_wsmDia).filter((v): v is number => v != null);
  const diaMin = Math.min(...diaVals) ?? 0;
  const diaMax = Math.max(...diaVals) ?? 1;
  const diaSpan = Math.max(diaMax - diaMin, 1e-6);
  const diaPad = diaSpan * 0.1 || 1;

  const x = (m: MeasurementPoint) =>
    PAD.l + ((new Date(m.measurement_timestamp).getTime() - t0) / span) * (W - PAD.l - PAD.r);
  const yWear = (v: number) =>
    H - PAD.b - ((v - (wMin - wPad)) / (wSpan + 2 * wPad)) * (H - PAD.t - PAD.b);
  const yDia = (v: number) =>
    H - PAD.b - ((v - (diaMin - diaPad)) / (diaSpan + 2 * diaPad)) * (H - PAD.t - PAD.b);

  const line = (pts: [number, number][]) => {
    if (pts.length < 2) return "";
    let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    let lastX = pts[0][0];
    for (const [px, py] of pts.slice(1)) {
      if (Math.abs(px - lastX) > (W - PAD.l - PAD.r) * 0.02) d += ` M ${px.toFixed(1)} ${py.toFixed(1)}`;
      d += ` L ${px.toFixed(1)} ${py.toFixed(1)}`;
      lastX = px;
    }
    return d;
  };

  const wearPaths = WEAR.map((s) => ({
    ...s,
    d: line(measurements.map((m) => [x(m), yWear(s.get(m) ?? 0)] as [number, number])),
  }));
  const diaPath = line(measurements.map((m) => [x(m), yDia(m.mean_wsmDia ?? 0)] as [number, number]));

  const gridVals = [wMin, (wMin + wMax) / 2, wMax];
  const diaGrid = [diaMin, (diaMin + diaMax) / 2, diaMax];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="timeline">
      {gridVals.map((gv, i) => (
        <g key={`w${i}`}>
          <line x1={PAD.l} x2={W - PAD.r} y1={yWear(gv)} y2={yWear(gv)} stroke="#eee" />
          <text x={PAD.l - 6} y={yWear(gv) + 3} textAnchor="end" fontSize="10" fill="#888">
            {gv.toFixed(2)}
          </text>
        </g>
      ))}
      <text x={6} y={PAD.t + 8} fontSize="10" fill="#888" transform="rotate(-90 10 20)">
        wear (mm)
      </text>

      {diaGrid.map((gv, i) => (
        <text key={`d${i}`} x={W - PAD.r + 6} y={yDia(gv) + 3} fontSize="10" fill="#1f77b4">
          {gv.toFixed(1)}
        </text>
      ))}
      <text x={W - 8} y={PAD.t + 8} fontSize="10" fill="#1f77b4" textAnchor="end">
        dia (mm)
      </text>

      {measurements.map((m, i) =>
        m.turn_event ? (
          <circle
            key={`t${i}`}
            cx={x(m)}
            cy={yWear(m.mean_wsmFlange ?? 0)}
            r={4}
            fill="none"
            stroke="#f39c12"
            strokeWidth={2}
          />
        ) : null
      )}

      <path d={diaPath} fill="none" stroke="#1f77b4" strokeWidth={1.8} opacity={0.85} />
      {wearPaths.map((p) => (
        <path key={p.key} d={p.d} fill="none" stroke={p.color} strokeWidth={1.7} />
      ))}

      <g transform={`translate(${PAD.l}, ${PAD.t + 2})`}>
        {[...WEAR.map((s) => ({ key: s.key, color: s.color })), { key: "wsmDia", color: "#1f77b4" }].map(
          (s, i) => (
            <g key={s.key} transform={`translate(${i * 92}, 0)`}>
              <line x1={0} x2={12} y1={0} y2={0} stroke={s.color} strokeWidth={2} />
              <text x={16} y={3} fontSize="10" fill="#444">
                {s.key}
              </text>
            </g>
          )
        )}
      </g>
      <text x={W / 2} y={H - 6} fontSize="10" fill="#aaa" textAnchor="middle">
        time
      </text>
    </svg>
  );
}
