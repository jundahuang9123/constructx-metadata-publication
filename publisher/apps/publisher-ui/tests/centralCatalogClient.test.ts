import { describe, expect, it } from "vitest";
import { publishToCentralCatalog } from "../src/publisher/centralCatalogClient";

describe("publishToCentralCatalog", () => {
  const payload = {
    body: "@prefix dcat: <http://www.w3.org/ns/dcat#> .",
    contentType: "text/turtle",
    sourceLabel: "catalog.ttl"
  };

  it("posts RDF to the central catalogue with WebID and manual token headers", async () => {
    const calls: Request[] = [];
    const fakeFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(new Request(input, init));
      return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    };

    const result = await publishToCentralCatalog({
      targetUrl: "http://catalog.example/catalog",
      payload,
      webId: "https://pod.example/alice/profile/card#me",
      token: "abc",
      authFetch: fakeFetch
    });

    expect(result.ok).toBe(true);
    expect(calls[0].headers.get("X-Participant-WebID")).toContain("alice");
    expect(calls[0].headers.get("Authorization")).toBe("Bearer abc");
    expect(calls[0].headers.get("Content-Type")).toBe("text/turtle");
  });

  it("does not set manual Authorization when token override is omitted", async () => {
    const calls: Request[] = [];
    const fakeFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(new Request(input, init));
      return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    };

    const result = await publishToCentralCatalog({
      targetUrl: "http://catalog.example/catalog",
      payload,
      webId: "https://pod.example/alice/profile/card#me",
      authFetch: fakeFetch
    });

    expect(result.ok).toBe(true);
    expect(calls[0].headers.get("Authorization")).toBeNull();
    expect(calls[0].headers.get("X-Participant-WebID")).toContain("alice");
    expect(calls[0].headers.get("X-Participant-Id")).toContain("alice");
    expect(calls[0].headers.get("Content-Type")).toBe("text/turtle");
  });
});
