import { useEffect, useState } from "react";
import { api } from "./api";
import type { ModelHealth, PturnHealthCell } from "./types";
import { EmptyState, ErrorState, SkeletonBlock } from "./States";

const DIM_ORDER = ["wsmFlange", "wsmRoot", "wsmThread", "wsmDia"] as const;
const HORIZONS = ["30", "90", "180"] as const;
const DIM_LABEL: Record<string, string> = {
  wsmFlange: "Flange",
  wsmRoot: "Root",
  wsmThread: "Thread",
  wsmDia: "Dia",
};

function fmt(v: number | null | undefined, d = 3): string {
  return v == null || !isFinite(v) ? "—" : v.toFixed(d);
}
function pct(v: number | null | undefined, d = 1): string {
  return v == null || !isFinite(v) ? "—" : (v * 100).toFixed(d) + "%";
}

function healthClass(v: number | null, good: "high" | "low"): string {
  if (v == null || !isFinite(v)) return "";
  if (good === "low") return v <= 0.2 ? "mh-good" : v <= 0.5 ? "mh-mid" : "mh-bad";
  return v >= 0.7 ? "mh-good" : v >= 0.4 ? "mh-mid" : "mh-bad";
}

function DegradationTable({ degradation }: { degradation: ModelHealth["degradation"] }) {
  const dims = DIM_ORDER.filter((d) => degradation[d]);
  if (dims.length === 0) return null;
  return (
    <div className="mh-block">
      <h4>Degradation prediction quality (delta models, held-out split)</h4>
      <div className="table-wrap">
        <table className="risk-table mh-table">
          <thead>
            <tr>
              <th>Dim</th>
              <th>Horizon</th>
              <th>MAE (mm)</th>
              <th>ΔR²</th>
              <th>Spearman</th>
              <th>Noise floor (mm)</th>
              <th>80% band width</th>
              <th>Band coverage</th>
              <th>Capture@1%</th>
              <th>Capture@5%</th>
              <th>Capture@10%</th>
            </tr>
          </thead>
          <tbody>
            {dims.map((dim) => {
              const byH = degradation[dim];
              return HORIZONS.map((h) => {
                const c = byH[h];
                if (!c) return null;
                return (
                  <tr key={`${dim}-${h}`}>
                    <td>{DIM_LABEL[dim] ?? dim}</td>
                    <td>{h}d</td>
                    <td className={`mono ${healthClass(c.mae_mm, "low")}`}>{fmt(c.mae_mm)}</td>
                    <td className={`mono ${healthClass(c.r2, "high")}`}>{c.r2 == null ? "—" : c.r2.toFixed(3)}</td>
                    <td className={`mono ${healthClass(c.spearman, "high")}`}>{c.spearman == null ? "—" : c.spearman.toFixed(3)}</td>
                    <td className="mono">{fmt(c.noise_floor_mm)}</td>
                    <td className="mono">{fmt(c.conformal?.width_mm)}</td>
                    <td className={`mono ${healthClass(c.conformal?.coverage, "high")}`}>
                      {c.conformal?.coverage == null
                        ? "—"
                        : (c.conformal.coverage * 100).toFixed(0) + "%"}
                    </td>
                    <td className="mono">{pct(c.capture_at_1_pct)}</td>
                    <td className="mono">{pct(c.capture_at_5_pct)}</td>
                    <td className="mono">{pct(c.capture_at_10_pct)}</td>
                  </tr>
                );
              });
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PturnTable({ pturn }: { pturn: ModelHealth["pturn"] }) {
  const hs = Object.keys(pturn).sort((a, b) => Number(a) - Number(b));
  if (hs.length === 0) return null;
  return (
    <div className="mh-block">
      <h4>P(turn) reliability (C1 XGB, Phase 4 benchmark)</h4>
      <div className="table-wrap">
        <table className="risk-table mh-table">
          <thead>
            <tr>
              <th>Horizon</th>
              <th>ROC-AUC</th>
              <th>PR-AUC</th>
              <th>Brier</th>
              <th>ECE</th>
              <th>Train rate</th>
              <th>Test rate</th>
              <th>n_test</th>
            </tr>
          </thead>
          <tbody>
            {hs.map((h) => {
              const m: PturnHealthCell = pturn[h];
              return (
                <tr key={h}>
                  <td>{h}d</td>
                  <td className={`mono ${healthClass(m.roc_auc, "high")}`}>{m.roc_auc == null ? "—" : m.roc_auc.toFixed(3)}</td>
                  <td className={`mono ${healthClass(m.pr_auc, "high")}`}>{m.pr_auc == null ? "—" : m.pr_auc.toFixed(3)}</td>
                  <td className={`mono ${healthClass(m.brier, "low")}`}>{fmt(m.brier)}</td>
                  <td className="mono">{fmt(m.ece)}</td>
                  <td className="mono">{pct(m.turn_rate_train)}</td>
                  <td className="mono">{pct(m.turn_rate_test)}</td>
                  <td className="mono">{m.n_test?.toLocaleString() ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ModelHealthPanel() {
  const [data, setData] = useState<ModelHealth | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setData(null);
    setErr(null);
    api
      .modelHealth()
      .then(setData)
      .catch((e) => setErr((e as Error).message));
  }, [reload]);

  if (err) return <ErrorState message={err} onRetry={() => setReload((r) => r + 1)} />;
  if (!data) return <SkeletonBlock lines={6} />;

  const prov = data.provenance;
  return (
    <section className="model-health">
      <h3>Model health</h3>
      <p className="muted small mh-note">
        Every number maps 1:1 to the committed benchmark artifacts
        (<code>trajectory_product_analysis.json</code> +{" "}
        <code>turn_probability_benchmark.json</code>) — held-out self-assessment,
        not a live probe.
        {prov?.artefact_generated ? ` Artefact generated ${prov.artefact_generated}.` : ""}
      </p>
      <DegradationTable degradation={data.degradation} />
      <PturnTable pturn={data.pturn} />
      {!data.degradation && !data.pturn && (
        <EmptyState title="No model-health data" hint="The benchmark artifacts are missing." />
      )}
    </section>
  );
}