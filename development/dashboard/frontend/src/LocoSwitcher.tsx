import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { LocoSwitcherItem } from "./types";

/** Loco switcher: prev/next + dropdown navigation across all locos in the
 *  fleet snapshot. Read-only navigation aid — the fleet list is the same
 *  snapshot contract the fleet view uses (ordered by loco number). */
export function LocoSwitcher({
  loco,
  onNavigate,
}: {
  loco: string;
  onNavigate: (locoNumber: string) => void;
}) {
  const [locos, setLocos] = useState<LocoSwitcherItem[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setErr(null);
    api
      .fleetLocos()
      .then((r) => setLocos(r.locos))
      .catch((e) => setErr((e as Error).message));
  }, []);

  const items = useMemo(() => locos.filter((l) => l.loco_number !== loco), [locos, loco]);
  const idx = locos.findIndex((l) => l.loco_number === loco);
  const prev = idx > 0 ? locos[idx - 1] : null;
  const next = idx >= 0 && idx < locos.length - 1 ? locos[idx + 1] : null;

  const go = (target: string) => {
    if (target && target !== loco) onNavigate(target);
  };

  return (
    <div className="loco-switcher" aria-label="Loco switcher">
      <button
        className="btn btn-sm"
        disabled={!prev}
        onClick={() => prev && go(prev.loco_number)}
        title={prev ? `Previous loco ${prev.loco_number}` : "First loco"}
      >
        ‹ prev
      </button>
      <select
        className="loco-switcher-select mono"
        value={loco}
        onChange={(e) => go(e.target.value)}
        aria-label="Jump to loco"
      >
        <option value={loco}>{loco} (current)</option>
        {items.map((l) => (
          <option key={l.loco_number} value={l.loco_number}>
            {l.loco_number} · {l.n_wheelsets} ws
          </option>
        ))}
      </select>
      <button
        className="btn btn-sm"
        disabled={!next}
        onClick={() => next && go(next.loco_number)}
        title={next ? `Next loco ${next.loco_number}` : "Last loco"}
      >
        next ›
      </button>
      {err && <span className="muted small">{err}</span>}
    </div>
  );
}