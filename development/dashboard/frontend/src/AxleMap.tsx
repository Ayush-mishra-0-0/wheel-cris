import type { LocoWheelsetRow } from "./types";

/** Compact "which axle is hot" visual. Renders 6 axle boxes (Co-Co) with a
 *  left/right wheel slot each, coloured by proximity to the approved 1016 mm
 *  dia hard stop. Clicking a wheel opens that wheelset. Honest fallback: if
 *  the snapshot has no axle/position info for a row, it is omitted. */
function sev(days: number | null | undefined): "ok" | "warn" | "danger" {
  if (days == null || !isFinite(days)) return "ok";
  if (days <= 30) return "danger";
  if (days <= 180) return "warn";
  return "ok";
}

function axleSide(r: LocoWheelsetRow): { axle: number; side: string } | null {
  if (r.axle_position_1_6 != null) {
    return { axle: Math.max(1, Math.min(6, r.axle_position_1_6)), side: "·" };
  }
  const pos = r.wheel_position_1_12;
  if (pos == null || !isFinite(pos) || pos < 1 || pos > 12) return null;
  return { axle: ((pos - 1) % 6) + 1, side: pos <= 6 ? "A" : "B" };
}

export function AxleMap({
  rows,
  selected,
  onSelect,
}: {
  rows: LocoWheelsetRow[];
  selected: number | null;
  onSelect: (ws: number) => void;
}) {
  const byAxle = buildAxleMap(rows);
  if (byAxle.length === 0) return null;

  return (
    <div className="axle-map" aria-label="Axle position map">
      {byAxle.map(({ axle, wheels }) => {
        const hottest = wheels.reduce<LocoWheelsetRow | null>(
          (a, b) => {
            const da = a ? (a.days_to_condemning_dia ?? Infinity) : Infinity;
            const db = b.days_to_condemning_dia ?? Infinity;
            return db < da ? b : a;
          },
          null
        );
        const level = sev(hottest?.days_to_condemning_dia);
        return (
          <div key={axle} className={`axle-box axle-${level}`}>
            <button
              className="axle-label"
              onClick={() => hottest && onSelect(hottest.wheelset_equipment_id)}
              title={wheels.map((w) => `#${w.wheelset_equipment_id} dia ${w.latest_mean_wsmDia?.toFixed(1) ?? "—"} mm`).join("\n")}
            >
              {axle}
            </button>
            {wheels.map((w) => {
              const s = sev(w.days_to_condemning_dia);
              const isSel = w.wheelset_equipment_id === selected;
              return (
                <button
                  key={w.wheelset_equipment_id}
                  className={`axle-wheel axle-wheel-${s}${isSel ? " axle-wheel-selected" : ""}`}
                  onClick={() => onSelect(w.wheelset_equipment_id)}
                  title={`#${w.wheelset_equipment_id} · dia ${w.latest_mean_wsmDia?.toFixed(1) ?? "—"} mm · condemning ${w.days_to_condemning_dia != null ? `${w.days_to_condemning_dia.toFixed(0)} d` : "—"}`}
                >
                  <span className="mono">#{w.wheelset_equipment_id}</span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function buildAxleMap(rows: LocoWheelsetRow[]) {
  const byAxle = new Map<number, LocoWheelsetRow[]>();
  for (const r of rows) {
    const info = axleSide(r);
    if (!info) continue;
    if (!byAxle.has(info.axle)) byAxle.set(info.axle, []);
    byAxle.get(info.axle)!.push(r);
  }
  return Array.from(byAxle.entries())
    .sort(([a], [b]) => a - b)
    .map(([axle, wheels]) => ({ axle, wheels }));
}
