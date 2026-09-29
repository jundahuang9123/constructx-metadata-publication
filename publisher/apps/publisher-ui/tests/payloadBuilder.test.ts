import { describe, expect, it } from "vitest";
import { buildPublishPayload } from "../src/publisher/payloadBuilder";

describe("buildPublishPayload", () => {
  it("preserves original RDF and content type", () => {
    const payload = buildPublishPayload({
      sourceKind: "file",
      sourceLabel: "catalog.ttl",
      rdf: "@prefix dcat: <http://www.w3.org/ns/dcat#> .",
      contentType: "text/turtle"
    });

    expect(payload.body).toContain("@prefix dcat");
    expect(payload.contentType).toBe("text/turtle");
    expect(payload.sourceLabel).toBe("catalog.ttl");
  });
});

