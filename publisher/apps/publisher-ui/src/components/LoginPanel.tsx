import { SolidSessionState } from "../solid/session";

interface Props {
  idp: string;
  onIdpChange: (value: string) => void;
  sessionState: SolidSessionState | null;
  onLogin: () => void;
  onLogout: () => void;
}

export function LoginPanel({ idp, onIdpChange, sessionState, onLogin, onLogout }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="step">1</span>
        <div>
          <h2>Login</h2>
          <p>Authenticate with a Solid identity provider.</p>
        </div>
      </div>
      <label>
        Identity provider
        <input value={idp} onChange={(event) => onIdpChange(event.target.value)} />
      </label>
      <div className="button-row">
        <button onClick={onLogin} type="button">
          Login with Solid
        </button>
        <button className="secondary" onClick={onLogout} type="button">
          Logout
        </button>
      </div>
      <div className="status-line">
        <span>Authenticated WebID</span>
        <strong>{sessionState?.webId || "Not logged in"}</strong>
      </div>
    </section>
  );
}

