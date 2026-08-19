export function LimitChip({ dim }: { dim: string | null }) {
  if (!dim) return <span>—</span>;
  const cls = dim.startsWith("wsm") ? `limit-dim lim-${dim}` : "limit-dim";
  return <span className={cls}>{dim}</span>;
}

const WEAR_LABELS: Record<string, string> = {
  wsmRoot: "R",
  wsmFlange: "F",
  wsmThread: "T",
};

/** Secondary wear watch-bands (display-only colour convention, never ranked). */
export function WearBands({ bands }: { bands?: Record<string, { band: string; headroom: number | null; limit_mm: number | null }> }) {
  if (!bands || Object.keys(bands).length === 0) return <span className="muted small">—</span>;
  return (
    <span className="wear-bands">
      {Object.entries(bands).map(([dim, b]) => (
        <span
          key={dim}
          className={`wear-band wear-band-${b.band}`}
          title={`${dim} → approved ${b.limit_mm} mm (Wrpld) · headroom ${b.headroom == null ? "—" : Math.round(b.headroom * 100) + "%"} · ${b.band} (watch-band, not a condemning threshold)`}
        >
          {WEAR_LABELS[dim] ?? dim.slice(3)}
        </span>
      ))}
    </span>
  );
}