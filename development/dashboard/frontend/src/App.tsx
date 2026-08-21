import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Capabilities, FleetBacktest, OperationalCapture, SearchHit } from "./types";
import { CaptureTable, FleetTable } from "./BacktestView";
import { DataHealthBanner } from "./DataHealthBanner";
import { FleetView } from "./FleetView";
import { LocoView } from "./LocoView";
import { ModelHealthPanel } from "./ModelHealthPanel";
import { ModelStrip } from "./ModelStrip";
import { ErrorState, SkeletonBlock } from "./States";

type Page = "fleet" | "validation" | "health" | "loco";

export function App() {
  const [page, setPage] = useState<Page>("fleet");
  const [loco, setLoco] = useState<string>("37597");
  const [preselectWs, setPreselectWs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);

  // global search (type-ahead)
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [showHits, setShowHits] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // hash deep links: #/loco/39186 or #/loco/39186?ws=123 → loco view (share/reload-safe); "" → fleet (back works)
  useEffect(() => {
    function applyHash() {
      const m = window.location.hash.match(/^#\/loco\/([^/]+)/);
      if (m) {
        setPage("loco");
        setLoco(decodeURIComponent(m[1]));
        const ws = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("ws");
        setPreselectWs(ws != null && /^\d+$/.test(ws) ? Number(ws) : null);
        setError(null);
      } else {
        setPage("fleet");
      }
    }
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

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

  async function openLoco(num: string, ws?: number) {
    setPage("loco");
    setLoco(num);
    setPreselectWs(ws ?? null);
    setError(null);
    setShowHits(false);
    const target = ws != null ? `#/loco/${encodeURIComponent(num)}?ws=${ws}` : `#/loco/${encodeURIComponent(num)}`;
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
  }

  function onWsChange(ws: number) {
    const target = `#/loco/${encodeURIComponent(loco)}?ws=${ws}`;
    if (window.location.hash !== target) {
      window.history.replaceState(null, "", target);
    }
  }

  function go(page: Page) {
    setPage(page);
    setError(null);
    if (page !== "loco") {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
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

      <ModelStrip caps={caps} />
      <DataHealthBanner health={caps?.data_health} />

      <div className="shell">
        <aside className="sidebar">
          <nav>
            <button className={page === "fleet" ? "nav-item active" : "nav-item"} onClick={() => go("fleet")}>
              Fleet
            </button>
            <button
              className={showHits && q.trim() ? "nav-item active" : "nav-item"}
              onClick={() => {
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
            <button
              className={page === "health" ? "nav-item active" : "nav-item"}
              onClick={() => go("health")}
            >
              Model health
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
              onSelect={(ws, locoNumber) => {
                if (locoNumber) {
                  openLoco(locoNumber, ws);
                }
              }}
            />
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

          {page === "health" && (
            <div className="health-page">
              <ModelHealthPanel />
            </div>
          )}

          {page === "loco" && (
            <LocoView loco={loco} caps={caps} preselectWs={preselectWs} onWsChange={onWsChange} onNavigateLoco={(num) => openLoco(num)} onBack={() => go("fleet")} />
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
