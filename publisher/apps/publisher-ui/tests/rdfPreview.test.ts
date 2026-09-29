import { describe, expect, it } from "vitest";
import { buildRdfPreview } from "../src/publisher/rdfPreview";

const turtle = `
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix dct: <http://purl.org/dc/terms/> .

<https://example.org/catalog> a dcat:Catalog ;
  dcat:dataset <https://example.org/datasets/one> .

<https://example.org/datasets/one> a dcat:Dataset ;
  dct:title "Dataset One" ;
  dcat:distribution <https://example.org/datasets/one/dist> .

<https://example.org/datasets/one/dist> a dcat:Distribution ;
  dcat:downloadURL <https://example.org/data/one.csv> ;
  dcat:mediaType "text/csv" .
`;

describe("buildRdfPreview", () => {
  it("extracts DCAT counts and dataset rows", () => {
    const preview = buildRdfPreview(turtle, "text/turtle");

    expect(preview.catalogIris).toEqual(["https://example.org/catalog"]);
    expect(preview.datasetCount).toBe(1);
    expect(preview.distributionCount).toBe(1);
    expect(preview.datasets[0].title).toBe("Dataset One");
    expect(preview.datasets[0].accessUrls).toEqual(["https://example.org/data/one.csv"]);
  });

  it("reports parse warnings for malformed RDF", () => {
    const preview = buildRdfPreview("not rdf", "text/turtle");

    expect(preview.parseError).toBeTruthy();
    expect(preview.warnings).toContain("Could not parse RDF for preview.");
  });

  it("extracts a simple JSON-LD catalogue preview", () => {
    const preview = buildRdfPreview(
      JSON.stringify({
        "@id": "https://example.org/catalog-jsonld",
        "@type": "dcat:Catalog",
        "dcat:dataset": {
          "@id": "https://example.org/datasets/jsonld",
          "@type": "dcat:Dataset",
          "dct:title": "JSON-LD Dataset",
          "dcat:distribution": {
            "@id": "https://example.org/datasets/jsonld/dist",
            "@type": "dcat:Distribution",
            "dcat:downloadURL": { "@id": "https://example.org/data/jsonld.csv" },
            "dcat:mediaType": "text/csv"
          }
        }
      }),
      "application/ld+json"
    );

    expect(preview.catalogIris).toEqual(["https://example.org/catalog-jsonld"]);
    expect(preview.datasetCount).toBe(1);
    expect(preview.distributionCount).toBe(1);
    expect(preview.datasets[0].title).toBe("JSON-LD Dataset");
  });
});
