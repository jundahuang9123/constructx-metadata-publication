interface Props {
  catalogUrl: string;
  webIdInput: string;
  onCatalogUrlChange: (value: string) => void;
  onWebIdInputChange: (value: string) => void;
  onResolveWebId: () => void;
  onFetch: () => void;
  onFile: (file: File) => void;
  warning?: string;
}

export function CatalogSourcePanel({
  catalogUrl,
  webIdInput,
  onCatalogUrlChange,
  onWebIdInputChange,
  onResolveWebId,
  onFetch,
  onFile,
  warning
}: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="step">2</span>
        <div>
          <h2>Select Catalogue</h2>
          <p>Fetch from a Pod URL, infer from WebID, or upload a local RDF file.</p>
        </div>
      </div>
      <label>
        Direct catalogue URL
        <input
          placeholder="https://pod.example/alice/catalog/cat.ttl"
          value={catalogUrl}
          onChange={(event) => onCatalogUrlChange(event.target.value)}
        />
      </label>
      <div className="split-row">
        <label>
          WebID-based resolution
          <input
            placeholder="https://pod.example/alice/profile/card#me"
            value={webIdInput}
            onChange={(event) => onWebIdInputChange(event.target.value)}
          />
        </label>
        <button className="secondary" type="button" onClick={onResolveWebId}>
          Infer URL
        </button>
      </div>
      <label>
        Local RDF file
        <input
          type="file"
          accept=".ttl,.json,.jsonld,text/turtle,application/ld+json"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
          }}
        />
      </label>
      {warning ? <p className="warning">{warning}</p> : null}
      <button type="button" onClick={onFetch}>
        Fetch Catalogue URL
      </button>
    </section>
  );
}

