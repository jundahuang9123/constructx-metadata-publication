// Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
export function getPodRoot(webId: string): string {
  if (!webId) return "";
  const url = new URL(webId);
  const segments = url.pathname.split("/").filter(Boolean);
  const profileIndex = segments.indexOf("profile");
  const baseSegments = profileIndex > -1 ? segments.slice(0, profileIndex) : segments;
  const basePath = baseSegments.length ? `/${baseSegments.join("/")}/` : "/";
  return `${url.origin}${basePath}`;
}

export function inferCatalogUrlFromWebId(webId: string): { url: string; warning?: string } {
  if (!webId) {
    return { url: "", warning: "Enter a WebID before resolving a catalogue URL." };
  }

  try {
    return {
      url: `${getPodRoot(webId)}catalog/cat.ttl`,
      warning:
        "Catalogue URL inferred from the common <pod-root>/catalog/cat.ttl convention. Confirm it before publishing."
    };
  } catch {
    return { url: "", warning: "Could not parse the WebID. Use an explicit catalogue URL." };
  }
}

