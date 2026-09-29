# Publisher Auth Findings

Date: 2026-06-23

## Phase 0 Status

Pending real Solid-OIDC capture.

This repository now has a request catcher for Phase 0, but this environment does
not have the real Solid login, registry, and catalogue runtime needed to capture
an authenticated browser push. Do not claim the strict OIDC path is secure
end-to-end until that run has happened.

## Static Finding

The browser publisher calls `publishToCentralCatalog` with the authenticated
Solid `session.fetch` when a session is available.

When no access-token override is entered, the publisher sets only:

- `Content-Type`
- `X-Participant-WebID`
- `X-Participant-Id`

It does not create its own `Authorization` header in this path. That leaves the
actual Solid auth headers to Inrupt's `session.fetch`, which may attach
`Authorization` and `DPoP` for the central catalogue URL. This must be verified
with the real request catcher run.

When an access-token override is entered, the publisher sends:

```http
Authorization: Bearer <override>
```

That override is a plain bearer path. It is useful for local development or a
catalogue running in `trusted-header` mode, but it is not expected to satisfy a
strict DPoP-validating catalogue unless the catalogue is deliberately configured
to accept non-DPoP bearer tokens.

The sibling catalogue's default `SOLID_AUTH_MODE=oidc` path requires DPoP when
`SOLID_AUTH_REQUIRE_DPOP=true`, which is the default.

## Running Phase 0

Start the catcher:

```bash
python tools/catch-publisher-request/catch_push.py --port 8787
```

Start the publisher UI:

```bash
npm run dev
```

In the browser:

1. Log in with a real Solid-OIDC identity.
2. Load or upload a catalogue.
3. Set the central catalogue URL to `http://localhost:8787/catalog`.
4. Leave the access-token override empty.
5. Publish.

Inspect the catcher output:

- Is there a `DPoP` header?
- Does the access-token payload include `cnf.jkt`?
- Do the DPoP proof claims include `htu=http://localhost:8787/catalog` and
  `htm=POST`?
- Does the DPoP proof header include a public `jwk`?

## Interpreting The Result

Case A: `session.fetch` sends a valid DPoP proof for the target URL and the token
has `cnf.jkt`.

The strict catalogue path may already be aligned. Move to end-to-end verification
against the real catalogue, registry, and Fuseki.

Case B: the request sends a token but no DPoP proof, or the token is not
DPoP-bound.

Strict catalogue OIDC will reject the push. The publisher needs a real DPoP
solution, preferably by making the built-in `session.fetch` path work before
attempting manual proof construction.

Case C: DPoP exists but is bound to the wrong URL or method.

The publisher needs to ensure the proof is generated for the exact central
catalogue `POST` URL and method.

## Current Alignment

- Demo path: catalogue `SOLID_AUTH_MODE=trusted-header`; publisher can send the
  WebID headers and, optionally, a manual bearer token.
- Strict path: catalogue `SOLID_AUTH_MODE=oidc` with
  `SOLID_AUTH_REQUIRE_DPOP=true`; publisher must use a real Solid session whose
  push request carries valid DPoP. This is pending Phase 0 capture.
- Manual override: plain bearer only, not proof-of-possession.
