import type { DataHealth } from "./types";

function ageDays(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!isFinite(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

function fmtAge(iso: string | null | undefined): string {
  const d = ageDays(iso);
  return d == null ? "—" : d === 0 ? "today" : `${d} d ago`;
}

const STALE_DAYS = 14;

/** Data-health banner: how fresh is the data behind every number on screen. */
export function DataHealthBanner({ health }: { health?: DataHealth | null }) {
  if (!health || !health.items?.length) return null;
  const wesAge = ageDays(health.items.find((i) => i.name.startsWith("WES"))?.built_at);
  const stale = wesAge != null && wesAge > STALE_DAYS;
  const scopeFinal = (health.scope_status ?? "").endsWith("_SIGNOFF") ||
    (health.scope_status ?? "") === "DB_VERIFIED_PENDING_DOMAIN_SIGNOFF";
  return (
    <div
      className={`data-health-banner ${stale ? "data-health-stale" : ""}`}
      aria-label="Data freshness"
      title="Provenance freshness of the artifacts behind this dashboard (manifests only; no model outputs)."
    >
      <span className="data-health-title">data</span>
      {health.items.map((it) => (
        <span key={it.name} className={`data-health-item ${it.missing ? "data-health-missing" : ""}`}
          title={`${it.note}${it.path ? ` · ${it.path}` : ""}${it.rows != null ? ` · ${it.rows.toLocaleString()} rows` : ""}`}>
          <span className="data-health-label">{it.name}</span>
          <span className="mono">{fmtAge(it.built_at)}</span>
        </span>
      ))}
      {health.scope_status && (
        <span
          className={`chip ${scopeFinal ? "chip-reduced" : ""}`}
          title={scopeFinal
            ? "Trip-shed exclusion codes are DB-verified but await domain-owner sign-off — not release-final."
            : "Measurement-scope status"}
        >
          scope: {health.scope_status}
        </span>
      )}
    </div>
  );
}
