import {
  getDefaultSession,
  handleIncomingRedirect,
  login,
  logout,
  Session
} from "@inrupt/solid-client-authn-browser";

export interface SolidSessionState {
  session: Session;
  webId: string;
  isLoggedIn: boolean;
}

export async function restoreSession(): Promise<SolidSessionState> {
  await handleIncomingRedirect({ restorePreviousSession: true });
  const session = getDefaultSession();
  return {
    session,
    webId: session.info.webId || "",
    isLoggedIn: Boolean(session.info.isLoggedIn)
  };
}

export async function loginWithIssuer(issuer: string): Promise<void> {
  await login({
    oidcIssuer: issuer,
    redirectUrl: window.location.href,
    clientName: "Solid Federated Catalogue Publisher"
  });
}

export async function logoutSession(): Promise<void> {
  await logout();
}

export function getAuthenticatedFetch(session: Session): typeof fetch {
  return session.info.isLoggedIn ? session.fetch.bind(session) : fetch.bind(window);
}

