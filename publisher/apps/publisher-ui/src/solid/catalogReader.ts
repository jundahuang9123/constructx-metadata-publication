export type CatalogSourceKind = "url" | "file";

export interface LoadedCatalog {
  sourceKind: CatalogSourceKind;
  sourceLabel: string;
  rdf: string;
  contentType: string;
}

export function detectContentType(nameOrUrl: string, explicit?: string | null): string {
  const clean = (explicit || "").split(";")[0].trim().toLowerCase();
  if (clean.includes("text/turtle") || clean.includes("application/ld+json")) return clean;
  if (nameOrUrl.endsWith(".jsonld") || nameOrUrl.endsWith(".json")) return "application/ld+json";
  return "text/turtle";
}

export async function fetchCatalog(url: string, authFetch: typeof fetch): Promise<LoadedCatalog> {
  const response = await authFetch(url, {
    headers: { Accept: "text/turtle, application/ld+json;q=0.9" }
  });
  if (!response.ok) {
    throw new Error(`Catalogue fetch failed: ${response.status} ${response.statusText}`);
  }
  return {
    sourceKind: "url",
    sourceLabel: url,
    rdf: await response.text(),
    contentType: detectContentType(url, response.headers.get("content-type"))
  };
}

export async function readCatalogFile(file: File): Promise<LoadedCatalog> {
  return {
    sourceKind: "file",
    sourceLabel: file.name,
    rdf: await file.text(),
    contentType: detectContentType(file.name, file.type)
  };
}

