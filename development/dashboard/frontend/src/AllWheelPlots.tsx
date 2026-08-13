import { useEffect, useState } from "react";
import { api } from "./api";

export function AllWheelPlots({ loco }: { loco: string }) {
  const [images, setImages] = useState<Record<string, string> | null>(null);
  const [svgs, setSvgs] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setError(null);
    setImages(null);
    setSvgs(null);
    api
      .locoPlots(loco)
      .then((res) => {
        setImages(res.images ?? {});
        setSvgs(res.svgs ?? {});
      })
      .catch((e) => setError((e as Error).message));
  }, [loco]);

  if (error) return <div className="error">{error}</div>;
  if (!images && !svgs) return <p className="muted">Loading plots…</p>;

  const keys = Array.from(new Set([...(svgs ? Object.keys(svgs) : []), ...(images ? Object.keys(images) : [])]));
  const entries = keys.sort((a, b) => Number(a) - Number(b));

  return (
    <section className="lifecycle-plots">
      <h3>Lifecycle plots (all wheelsets)</h3>
      <div className="plots-grid">
        {entries.map((ws) => {
          const svg = svgs?.[ws];
          const png = images?.[ws];
          return (
            <div key={ws} className="plot-card">
              <h4>Wheelset #{ws}</h4>
              {svg ? (
                <div
                  className="svg-plot"
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              ) : png ? (
                png.startsWith("error:") ? (
                  <div className="muted">{png}</div>
                ) : (
                  <img src={`data:image/png;base64,${png}`} alt={`wheelset ${ws} lifecycle`} />
                )
              ) : (
                <div className="muted">No plot available</div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default AllWheelPlots;
