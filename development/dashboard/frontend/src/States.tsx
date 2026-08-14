export function SkeletonTable({ rows = 6, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table" aria-busy="true">
      <div className="skeleton-row skeleton-head">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="skeleton-cell skeleton-shimmer" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="skeleton-row">
          {Array.from({ length: cols }).map((_, i) => (
            <div key={i} className="skeleton-cell skeleton-shimmer" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-block" aria-busy="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton-line skeleton-shimmer" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-state">
      <div className="error">{message}</div>
      <button className="btn" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty-state">
      <div className="empty-title">{title}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}

export function StaleBanner({ days }: { days: number | null }) {
  if (days == null) return null;
  const stale = days > 7;
  return (
    <div className={stale ? "banner banner-warn" : "banner banner-ok"}>
      {stale
        ? `Snapshot is ${days} d old — forecasts may not reflect the latest turning history. Rebuild the fleet snapshot.`
        : `Snapshot refreshed ${days} d ago.`}
    </div>
  );
}
