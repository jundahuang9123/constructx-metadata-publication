# Catalogue And Publisher Integration Test

These steps verify this central catalogue with the sibling publisher directory:

```text
../publisher
```

The trusted-header path is the local demo baseline. The strict OIDC path requires
a real Solid login and a real request carrying a DPoP proof.

## Demo Path: Trusted Header

Start this catalogue:

```bash
SOLID_AUTH_MODE=trusted-header make up-solid
```

Start the publisher in the sibling repo:

```bash
cd ../publisher
npm run dev
```

In the publisher UI:

1. Open `http://localhost:5173`.
2. Load a valid DCAT catalogue from a Pod URL or local file.
3. Set the central catalogue URL to `http://localhost:8000/catalog`.
4. Publish.
5. Confirm the accepted dataset through `http://localhost:8000/datasets` or the
   catalogue UI.

Expected outcomes:

- Registered WebID and valid DCAT: `200`
- Unregistered WebID: `403`, stage `registry`
- Invalid RDF or invalid DCAT: `422`, stage `validation`

This path is for controlled demos only. It trusts `X-Participant-Id` or
`X-Participant-WebID`.

## Strict Path: Solid-OIDC With DPoP

First use the publisher request catcher to diagnose the real browser request:

```bash
cd ../publisher
python tools/catch-publisher-request/catch_push.py --port 8787
```

In the publisher UI, log in with a real Solid identity, leave the token override
empty, set the central catalogue URL to `http://localhost:8787/catalog`, and
publish.

The captured request must show:

- `Authorization` is present.
- The access-token payload includes `cnf.jkt`.
- `DPoP` is present.
- DPoP `htu` equals the exact POST URL.
- DPoP `htm` is `POST`.

Only after that capture is confirmed should the strict catalogue path be tested:

```bash
SOLID_AUTH_MODE=oidc SOLID_AUTH_REQUIRE_DPOP=true make up-solid
```

Publish again from the browser to:

```text
http://localhost:8000/catalog
```

Expected outcome for a registered WebID and valid DCAT is `200`. Missing or
invalid DPoP should return `401`, stage `auth`.

## Evidence To Record

Record the result in the publisher's `docs/auth-findings.md`:

- Date and environment
- Solid IdP
- Registry URL
- Whether the request was Phase 0 Case A, B, or C
- Trusted-header response
- Strict OIDC response
- Screenshot paths, if captured
