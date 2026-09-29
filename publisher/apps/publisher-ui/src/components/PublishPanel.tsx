interface Props {
  centralUrl: string;
  token: string;
  disabled: boolean;
  onCentralUrlChange: (value: string) => void;
  onTokenChange: (value: string) => void;
  onPublish: () => void;
}

export function PublishPanel({
  centralUrl,
  token,
  disabled,
  onCentralUrlChange,
  onTokenChange,
  onPublish
}: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="step">4</span>
        <div>
          <h2>Publish</h2>
          <p>POST the RDF payload to the central federated catalogue.</p>
        </div>
      </div>
      <label>
        Central catalogue URL
        <input value={centralUrl} onChange={(event) => onCentralUrlChange(event.target.value)} />
      </label>
      <label>
        Access token override
        <input
          value={token}
          onChange={(event) => onTokenChange(event.target.value)}
          placeholder="Optional for local/dev central catalogue modes"
        />
      </label>
      <button disabled={disabled} onClick={onPublish} type="button">
        Publish Catalogue
      </button>
    </section>
  );
}

