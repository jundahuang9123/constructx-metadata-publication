import { LoadedCatalog } from "../solid/catalogReader";
import { RdfPreview } from "../publisher/rdfPreview";

interface Props {
  webId: string;
  centralUrl: string;
  catalog: LoadedCatalog | null;
  preview: RdfPreview | null;
}

export function PreviewPanel({ webId, centralUrl, catalog, preview }: Props) {
  return (
    <section className="panel wide">
      <div className="panel-heading">
        <span className="step">3</span>
        <div>
          <h2>Preview</h2>
          <p>Inspect the catalogue before publishing. The original RDF payload is preserved.</p>
        </div>
      </div>
      <div className="summary-grid">
        <Summary label="Authenticated WebID" value={webId || "Not logged in"} />
        <Summary label="Source" value={catalog?.sourceLabel || "-"} />
        <Summary label="Serialization" value={catalog?.contentType || "-"} />
        <Summary label="dcat:Catalog" value={preview?.catalogIris[0] || "-"} />
        <Summary label="Datasets" value={preview ? String(preview.datasetCount) : "-"} />
        <Summary label="Distributions" value={preview ? String(preview.distributionCount) : "-"} />
        <Summary label="Target" value={centralUrl} />
      </div>
      {preview?.warnings.length ? (
        <div className="warning-box">
          {preview.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
          {preview.parseError ? <pre>{preview.parseError}</pre> : null}
        </div>
      ) : null}
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Dataset IRI</th>
            <th>Distributions</th>
            <th>Access/download URL</th>
            <th>Format</th>
          </tr>
        </thead>
        <tbody>
          {(preview?.datasets || []).map((dataset) => (
            <tr key={dataset.iri}>
              <td>{dataset.title}</td>
              <td className="mono">{dataset.iri}</td>
              <td>{dataset.distributionCount}</td>
              <td className="mono">{dataset.accessUrls.join(", ") || "-"}</td>
              <td>{dataset.mediaTypes.join(", ") || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

