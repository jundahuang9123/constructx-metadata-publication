import { useEffect, useMemo, useState } from "react";
import { defaultCentralCatalogUrl, defaultIdp } from "./config";
import { LoginPanel } from "./components/LoginPanel";
import { CatalogSourcePanel } from "./components/CatalogSourcePanel";
import { PreviewPanel } from "./components/PreviewPanel";
import { PublishPanel } from "./components/PublishPanel";
import { ResultPanel } from "./components/ResultPanel";
import { HelpBox } from "./components/HelpBox";
import { LoadedCatalog, fetchCatalog, readCatalogFile } from "./solid/catalogReader";
import {
  SolidSessionState,
  getAuthenticatedFetch,
  loginWithIssuer,
  logoutSession,
  restoreSession
} from "./solid/session";
import { inferCatalogUrlFromWebId } from "./solid/webidResolver";
import { buildRdfPreview, RdfPreview } from "./publisher/rdfPreview";
import { buildPublishPayload } from "./publisher/payloadBuilder";
import { publishToCentralCatalog, PublishResult } from "./publisher/centralCatalogClient";

export function App() {
  const [idp, setIdp] = useState(defaultIdp);
  const [centralUrl, setCentralUrl] = useState(defaultCentralCatalogUrl);
  const [catalogUrl, setCatalogUrl] = useState("");
  const [webIdInput, setWebIdInput] = useState("");
  const [sourceWarning, setSourceWarning] = useState("");
  const [catalog, setCatalog] = useState<LoadedCatalog | null>(null);
  const [sessionState, setSessionState] = useState<SolidSessionState | null>(null);
  const [tokenOverride, setTokenOverride] = useState("");
  const [result, setResult] = useState<PublishResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    restoreSession()
      .then((state) => {
        setSessionState(state);
        if (state.webId) setWebIdInput(state.webId);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const preview: RdfPreview | null = useMemo(() => {
    if (!catalog) return null;
    return buildRdfPreview(catalog.rdf, catalog.contentType);
  }, [catalog]);

  const authFetch = sessionState?.session
    ? getAuthenticatedFetch(sessionState.session)
    : fetch.bind(window);

  async function handleFetchCatalog() {
    setError("");
    try {
      setCatalog(await fetchCatalog(catalogUrl, authFetch));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handlePublish() {
    if (!catalog) return;
    const parsedPreview = buildRdfPreview(catalog.rdf, catalog.contentType);
    if (parsedPreview.parseError) {
      setError("Malformed RDF blocks publishing. Fix the RDF and try again.");
      return;
    }
    setError("");
    try {
      setResult(
        await publishToCentralCatalog({
          targetUrl: centralUrl,
          payload: buildPublishPayload(catalog),
          webId: sessionState?.webId || webIdInput,
          token: tokenOverride || undefined,
          authFetch
        })
      );
    } catch (err) {
      setError(
        `Central catalogue could not be reached: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  function handleResolveWebId() {
    const resolved = inferCatalogUrlFromWebId(webIdInput);
    setCatalogUrl(resolved.url);
    setSourceWarning(resolved.warning || "");
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Solid publisher</p>
          <h1>Solid Federated Catalogue Publisher</h1>
          <p>Publish existing Solid DCAT catalogues to a central federated catalogue.</p>
        </div>
        <HelpBox />
      </header>
      <div className="grid">
        <LoginPanel
          idp={idp}
          onIdpChange={setIdp}
          sessionState={sessionState}
          onLogin={() => loginWithIssuer(idp)}
          onLogout={async () => {
            await logoutSession();
            setSessionState(await restoreSession());
          }}
        />
        <CatalogSourcePanel
          catalogUrl={catalogUrl}
          webIdInput={webIdInput}
          onCatalogUrlChange={setCatalogUrl}
          onWebIdInputChange={setWebIdInput}
          onResolveWebId={handleResolveWebId}
          onFetch={handleFetchCatalog}
          onFile={async (file) => setCatalog(await readCatalogFile(file))}
          warning={sourceWarning}
        />
        <PreviewPanel
          webId={sessionState?.webId || webIdInput}
          centralUrl={centralUrl}
          catalog={catalog}
          preview={preview}
        />
        <PublishPanel
          centralUrl={centralUrl}
          token={tokenOverride}
          disabled={!catalog}
          onCentralUrlChange={setCentralUrl}
          onTokenChange={setTokenOverride}
          onPublish={handlePublish}
        />
        <ResultPanel result={result} error={error} />
      </div>
      <footer>
        Built for Solid-based federated catalogue publishing. Builds on concepts from Florian
        Hoelken et al.'s semantic-data-catalog.
      </footer>
    </main>
  );
}

