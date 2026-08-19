export function LimitChip({ dim }: { dim: string | null }) {
  if (!dim) return <span>—</span>;
  const cls = dim.startsWith("wsm") ? `limit-dim lim-${dim}` : "limit-dim";
  return <span className={cls}>{dim}</span>;
}