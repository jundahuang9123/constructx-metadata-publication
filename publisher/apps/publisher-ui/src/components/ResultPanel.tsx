import { PublishResult } from "../publisher/centralCatalogClient";

interface Props {
  result: PublishResult | null;
  error: string;
}

export function ResultPanel({ result, error }: Props) {
  return (
    <section className="panel result-panel">
      <h2>Result</h2>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div className={result.ok ? "result-ok" : "result-fail"}>
          <strong>{result.ok ? "Publication successful." : "Publication rejected or failed."}</strong>
          <p>HTTP status: {result.status}</p>
          <pre>{result.body || "(empty response)"}</pre>
        </div>
      ) : (
        <p className="muted">No publication attempt yet.</p>
      )}
    </section>
  );
}

