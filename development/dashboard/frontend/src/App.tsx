import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Capabilities, FleetBacktest, OperationalCapture, SearchHit } from "./types";
import { CaptureTable, FleetTable } from "./BacktestView";
import { FleetView } from "./FleetView";
import { LocoView } from "./LocoView";
import { ErrorState, EmptyState, SkeletonBlock } from "./States";

type Page = "fleet" | "search" | "validation" | "loco";

export function App() {
  const [page, setPage] = useState<Page>("fleet");
  const [loco, setLoco] = useState<string>("37597");
  const [error, setError] = useState<string | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);

  // global search (type-ahead)
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [showHits, setShowHits] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .config()
      .then(setCaps)
      .catch(() => setCaps(null));
  }, []);

  // debounced type-ahead from /fleet/search
  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .fleetSearch(q.trim())
        .then((r) => setHits(r.items.slice(0, 8)))
        .catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  async function openLoco(num: string) {
    setPage("loco");
    setLoco(num);
    setError(null);
    setShowHits(false);
  }

  function go(page: Page) {
    setPage(page);
    setError(null);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          Wheel Lifecycle Dashboard
        </div>
        <div className="global-search" ref={searchRef}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onFocus={() => setShowHits(true)}
            onBlur={() => setTimeout(() => setShowHits(false), 150)}
            onKeyDown={(e) => e.key === "Enter" && hits[0]?.loco_number && openLoco(hits[0].loco_number)}
            placeholder="Search loco / shed / type…"
          />
          {showHits && q.trim() && (
            <div className="search-hits">
              {hits.length === 0 ? (
                <div className="search-hit muted">No matches for “{q}”</div>
              ) : (
                hits.map((h, i) => (
                  <button
                    key={i}
                    className="search-hit"
                    onMouseDown={() => h.loco_number && openLoco(h.loco_number)}
                  >
                    <span className="search-hit-loco">{h.loco_number ?? "—"}</span>
                    <span className="muted small">
                      {h.shed ?? ""}
                      {h.shed ? " · " : ""}
                      {h.loco_type ?? ""} · {h.n_wheelsets} ws
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </header>

      <div className="shell">
        <aside className="sidebar">
          <nav>
            <button className={page === "fleet" ? "nav-item active" : "nav-item"} onClick={() => go("fleet")}>
              Fleet
            </button>
            <button
              className={page === "search" ? "nav-item active" : "nav-item"}
              onClick={() => {
                go("search");
                setShowHits(true);
                searchRef.current?.focus();
              }}
            >
              Search
            </button>
            <button
              className={page === "validation" ? "nav-item active" : "nav-item"}
              onClick={() => go("validation")}
            >
              Validation / Backtest
            </button>
          </nav>
          {page === "loco" && (
            <div className="sidebar-sub">
              <button className="nav-item back" onClick={() => go("fleet")}>
                ← Back to fleet
              </button>
            </div>
          )}
        </aside>

        <main className="content">
          {error && <div className="error">{error}</div>}

          {page === "fleet" && (
            <FleetView
              onSelect={(_ws, locoNumber) => {
                if (locoNumber) {
                  openLoco(locoNumber);
                }
              }}
            />
          )}

          {page === "search" && (
            <div className="search-page">
              <h2>Search</h2>
              <p className="muted">Type a loco number, shed or loco type in the top bar.</p>
              {!q.trim() ? (
                <EmptyState title="Type to search" hint="Start typing a loco number, shed or loco type in the top search bar." />
              ) : hits.length === 0 ? (
                <EmptyState title={`No matches for “${q}”`} hint="Try a different loco number, shed code or loco type." />
              ) : (
                <ul className="search-results">
                  {hits.map((h, i) => (
                    <li key={i}>
                      <button className="search-result" onClick={() => h.loco_number && openLoco(h.loco_number)}>
                        <b>{h.loco_number}</b>
                        <span className="muted">
                          {h.shed} · {h.loco_type} · {h.n_wheelsets} wheelsets
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {page === "validation" && (
            <div className="validation-page">
              <h2>Validation / Backtest</h2>
              <p className="muted small">
                Fleet-level metrics from <code>/backtest/fleet</code>. For wheelset-level replay,
                open a loco from Fleet or Search and use the wheelset tabs.
              </p>
              <FleetValidation />
            </div>
          )}

          {page === "loco" && (
            <LocoView loco={loco} caps={caps} onBack={() => go("fleet")} />
          )}
        </main>
      </div>
    </div>
  );
}

function FleetValidation() {
  const [fleet, setFleet] = useState<FleetBacktest | null>(null);
  const [capture, setCapture] = useState<OperationalCapture | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setFleet(null);
    setErr(null);
    api
      .fleetBacktest()
      .then(setFleet)
      .catch((e) => setErr((e as Error).message));
    api
      .fleetCapture()
      .then(setCapture)
      .catch(() => {}); // capture@k is optional enrichment, not a hard dependency
  }, [reload]);

  if (err) return <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />;
  if (!fleet) return <SkeletonBlock lines={8} />;

  return (
    <div className="backtest">
      <FleetTable fleet={fleet} />
      {capture && <CaptureTable capture={capture} />}
    </div>
  );
}
