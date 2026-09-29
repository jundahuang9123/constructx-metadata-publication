import { Parser, Quad, Store } from "n3";

const DCAT = "http://www.w3.org/ns/dcat#";
const DCTERMS = "http://purl.org/dc/terms/";
const RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

export interface DatasetPreview {
  iri: string;
  title: string;
  distributionCount: number;
  accessUrls: string[];
  mediaTypes: string[];
}

export interface RdfPreview {
  catalogIris: string[];
  datasetCount: number;
  distributionCount: number;
  datasets: DatasetPreview[];
  warnings: string[];
  parseError?: string;
}

function parseQuads(rdf: string, contentType: string): Quad[] {
  const format = contentType.includes("ld+json") ? "application/ld+json" : "text/turtle";
  const parser = new Parser({ format });
  return parser.parse(rdf);
}

function asArray<T>(value: T | T[] | undefined): T[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function compactJsonLdValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record["@id"] === "string") return record["@id"];
    if (typeof record["@value"] === "string") return record["@value"];
  }
  return "";
}

function jsonLdTypes(node: Record<string, unknown>): string[] {
  return asArray(node["@type"]).map(compactJsonLdValue);
}

function jsonLdId(node: Record<string, unknown>): string {
  return typeof node["@id"] === "string" ? node["@id"] : "";
}

function walkJsonLd(value: unknown, nodes: Record<string, unknown>[]): void {
  if (Array.isArray(value)) {
    value.forEach((item) => walkJsonLd(item, nodes));
    return;
  }
  if (!value || typeof value !== "object") return;
  const record = value as Record<string, unknown>;
  if (record["@id"] || record["@type"]) nodes.push(record);
  Object.values(record).forEach((item) => walkJsonLd(item, nodes));
}

function previewJsonLd(rdf: string): RdfPreview {
  const parsed = JSON.parse(rdf) as unknown;
  const nodes: Record<string, unknown>[] = [];
  walkJsonLd(parsed, nodes);
  const isType = (node: Record<string, unknown>, type: string) =>
    jsonLdTypes(node).some((nodeType) => nodeType === type || nodeType.endsWith(type));
  const catalogs = nodes.filter((node) => isType(node, "Catalog"));
  const datasets = nodes.filter((node) => isType(node, "Dataset"));
  const distributions = nodes.filter((node) => isType(node, "Distribution"));
  const warnings: string[] = [];
  if (!catalogs.length) warnings.push("No dcat:Catalog detected.");
  if (!datasets.length) warnings.push("No dcat:Dataset detected.");
  if (!distributions.length) warnings.push("No dcat:Distribution detected.");

  return {
    catalogIris: catalogs.map(jsonLdId).filter(Boolean),
    datasetCount: datasets.length,
    distributionCount: distributions.length,
    warnings,
    datasets: datasets.map((dataset) => {
      const distributionNodes = asArray(dataset["dcat:distribution"]).filter(
        (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object"
      );
      return {
        iri: jsonLdId(dataset),
        title: compactJsonLdValue(dataset["dct:title"]) || "(untitled)",
        distributionCount: distributionNodes.length,
        accessUrls: distributionNodes
          .flatMap((distribution) => [
            ...asArray(distribution["dcat:accessURL"]),
            ...asArray(distribution["dcat:downloadURL"])
          ])
          .map(compactJsonLdValue)
          .filter(Boolean),
        mediaTypes: distributionNodes
          .flatMap((distribution) => asArray(distribution["dcat:mediaType"]))
          .map(compactJsonLdValue)
          .filter(Boolean)
      };
    })
  };
}

function objectValues(store: Store, subject: string, predicate: string): string[] {
  return store.getObjects(subject, predicate, null).map((term) => term.value);
}

function firstLiteral(store: Store, subject: string, predicate: string): string {
  return objectValues(store, subject, predicate)[0] || "";
}

export function buildRdfPreview(rdf: string, contentType: string): RdfPreview {
  if (contentType.includes("ld+json")) {
    try {
      return previewJsonLd(rdf);
    } catch (error) {
      return {
        catalogIris: [],
        datasetCount: 0,
        distributionCount: 0,
        datasets: [],
        warnings: ["Could not parse RDF for preview."],
        parseError: error instanceof Error ? error.message : String(error)
      };
    }
  }

  const warnings: string[] = [];
  let store: Store;

  try {
    store = new Store(parseQuads(rdf, contentType));
  } catch (error) {
    return {
      catalogIris: [],
      datasetCount: 0,
      distributionCount: 0,
      datasets: [],
      warnings: ["Could not parse RDF for preview."],
      parseError: error instanceof Error ? error.message : String(error)
    };
  }

  const catalogs = store.getSubjects(RDF_TYPE, `${DCAT}Catalog`, null).map((term) => term.value);
  const datasets = store.getSubjects(RDF_TYPE, `${DCAT}Dataset`, null).map((term) => term.value);
  const distributions = store
    .getSubjects(RDF_TYPE, `${DCAT}Distribution`, null)
    .map((term) => term.value);

  if (!catalogs.length) warnings.push("No dcat:Catalog detected.");
  if (!datasets.length) warnings.push("No dcat:Dataset detected.");
  if (!distributions.length) warnings.push("No dcat:Distribution detected.");

  return {
    catalogIris: catalogs,
    datasetCount: datasets.length,
    distributionCount: distributions.length,
    warnings,
    datasets: datasets.map((dataset) => {
      const distributionIris = objectValues(store, dataset, `${DCAT}distribution`);
      const accessUrls = distributionIris.flatMap((distribution) => [
        ...objectValues(store, distribution, `${DCAT}accessURL`),
        ...objectValues(store, distribution, `${DCAT}downloadURL`)
      ]);
      const mediaTypes = distributionIris.flatMap((distribution) =>
        objectValues(store, distribution, `${DCAT}mediaType`)
      );
      return {
        iri: dataset,
        title: firstLiteral(store, dataset, `${DCTERMS}title`) || "(untitled)",
        distributionCount: distributionIris.length,
        accessUrls,
        mediaTypes
      };
    })
  };
}
