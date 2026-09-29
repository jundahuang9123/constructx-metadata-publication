import { describe, expect, it } from "vitest";
import { detectContentType } from "../src/solid/catalogReader";
import { inferCatalogUrlFromWebId } from "../src/solid/webidResolver";

describe("catalogReader", () => {
  it("detects JSON-LD by extension", () => {
    expect(detectContentType("catalog.jsonld")).toBe("application/ld+json");
  });

  it("defaults to Turtle", () => {
    expect(detectContentType("catalog.ttl")).toBe("text/turtle");
  });

  it("infers catalogue URL from WebID convention", () => {
    const resolved = inferCatalogUrlFromWebId("https://pod.example/alice/profile/card#me");

    expect(resolved.url).toBe("https://pod.example/alice/catalog/cat.ttl");
    expect(resolved.warning).toContain("inferred");
  });
});

