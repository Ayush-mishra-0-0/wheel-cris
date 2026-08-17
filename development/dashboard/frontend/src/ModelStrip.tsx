import { useEffect, useState } from "react";
import { api } from "./api";
import type { Capabilities } from "./types";

/** Persistent model + policy status strip. Everything here is read-only
 *  server truth (config + fleet overview); it answers "what model am I
 *  looking at, how old is the snapshot, which limits are approved?" on every
 *  page without needing to open a specific wheelset. */
export function ModelStrip({ caps }: { caps: Capabilities | null }) {
  const [snapshotDays, setSnapshotDays] = useState<number | null>(null);
  const [modelVersion, setModelVersion] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState<string | null>(null);

  useEffect(() => {
    api
      .fleetOverview()
      .then((o) => {
        setSnapshotDays(
          o.snapshot_built_at
            ? Math.max(0, Math.floor((Date.now() - Date.parse(o.snapshot_built_at)) / 86400000))
            : null
        );
        if (o.model_version) setModelVersion(o.model_version);
        if (o.train_cutoff) setCutoff(o.train_cutoff);
      })
      .catch(() => {});
  }, []);

  const svc = caps?.degradation_serving;
  const model = modelVersion ?? svc?.model_version ?? "—";
  const cutoffLabel = cutoff ?? svc?.train_cutoff ?? "—";
  const limits = caps?.limits;

  return (
    <div className="model-strip" aria-label="Model and limit status">
      <span className="model-strip-item">
        <span className="model-strip-label">model</span>
        <span className="mono">{model}</span>
      </span>
      <span className="model-strip-item">
        <span className="model-strip-label">train cutoff</span>
        <span className="mono">{cutoffLabel}</span>
      </span>
      <span className="model-strip-item">
        <span className="model-strip-label">snapshot</span>
        <span>{snapshotDays == null ? "—" : `${snapshotDays} d ago`}</span>
      </span>
      <span className="model-strip-divider">·</span>
      <span className="model-strip-item">
        <span className="model-strip-label">limits</span>
        {limits && Object.keys(limits).length > 0 ? (
          <span className="model-strip-limits">
            {Object.entries(limits).map(([dim, r]) => (
              <span
                key={dim}
                className={`limit-chip limit-${r.status}`}
                title={`${r.label} · ${r.owner} · ${r.note}`}
              >
                {dim} {r.status}
                {r.limit_mm != null ? ` ${r.limit_mm} mm` : ""}
              </span>
            ))}
          </span>
        ) : (
          <span>…</span>
        )}
      </span>
    </div>
  );
}
