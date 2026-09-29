# Publisher And Catalogue Integration Test

These steps verify the publisher against the sibling central catalogue repo.
They separate the local demo path from the strict Solid-OIDC path so the tested
security claims stay clear.

## Prerequisites

- Publisher directory: `publisher`
- Catalogue directory: `../catalog`
- Docker with Compose for the catalogue stack
- A registry entry for the WebID used in the test
- For strict OIDC: a real Solid login and a real request from the browser UI

## Demo Path: Trusted Header

Start the catalogue in the sibling repo:

```bash
cd ../catalog
SOLID_AUTH_MODE=trusted-header make up-solid
```

Start the publisher:

```bash
npm run dev
```

In the browser:

1. Open `http://localhost:5173`.
2. Log in or use a local RDF file.
3. Set the central catalogue URL to `http://localhost:8000/catalog`.
4. Publish a valid DCAT catalogue.
5. Open `http://localhost:8000/datasets` or the catalogue UI to confirm storage.

Expected outcomes:

- Registered WebID and valid DCAT: `200`
- Unregistered WebID: `403`, stage `registry`
- Invalid RDF or invalid DCAT: `422`, stage `validation`

This mode is for controlled demos only. The catalogue trusts the declared
`X-Participant-Id` or `X-Participant-WebID` header.

## Strict Path: Solid-OIDC With DPoP

First capture the real browser push:

```bash
python tools/catch-publisher-request/catch_push.py --port 8787
```

In the publisher UI:

1. Log in with a real Solid-OIDC identity.
2. Load a catalogue from the Pod or a local file.
3. Set the central catalogue URL to `http://localhost:8787/catalog`.
4. Leave the access-token override empty.
5. Publish.

Confirm in the catcher output:

- `Authorization` is present.
- The access-token payload has `cnf.jkt`.
- `DPoP` is present.
- DPoP `htu` equals the exact POST URL.
- DPoP `htm` is `POST`.

If that capture is Case A in `docs/auth-findings.md`, start the strict
catalogue:

```bash
cd ../catalog
SOLID_AUTH_MODE=oidc SOLID_AUTH_REQUIRE_DPOP=true make up-solid
```

Then publish again from the browser to:

```text
http://localhost:8000/catalog
```

Expected outcome for a registered WebID and valid DCAT is `200`. A missing or
invalid DPoP proof should return `401`, stage `auth`.

## Manual Token Override

The token override field sends a plain bearer token. Use it only for local
experiments or catalogue modes that do not require DPoP. It is not the strict
OIDC path.

## Evidence To Record

After a real run, update `docs/auth-findings.md` with:

- Date and environment
- Solid IdP used
- Registry URL used
- Whether the request was Case A, B, or C
- Catalogue response for trusted-header and strict OIDC
- Screenshot path for the publisher and catalogue UI, if captured
