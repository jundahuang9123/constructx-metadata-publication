# Usage

## Browser UI

```bash
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

1. Log in with a Solid identity provider.
2. Enter a direct `catalog/cat.ttl` URL or infer one from a WebID.
3. Preview the DCAT summary and warnings.
4. Set the central catalogue URL.
5. Publish.

## Local File Demo

Local file upload lets you preview RDF without Solid login. Publishing may still fail if the central catalogue requires a real Solid-OIDC token.

For the sibling catalogue's local demo mode, start it with:

```bash
cd ../federated-catalog
SOLID_AUTH_MODE=trusted-header make up-solid
```

Then publish to `http://localhost:8000/catalog`. This mode trusts the declared
WebID header and is not a secure identity proof.

## Strict OIDC Publishing

For `SOLID_AUTH_MODE=oidc` with `SOLID_AUTH_REQUIRE_DPOP=true`, log in with a
real Solid identity and leave the access-token override empty. The browser path
delegates the push to Solid `session.fetch`, so the real request must be checked
before making a secure end-to-end claim:

```bash
python tools/catch-publisher-request/catch_push.py --port 8787
```

Set the central catalogue URL to `http://localhost:8787/catalog`, publish, and
inspect the captured `Authorization` and `DPoP` headers. See
`docs/auth-findings.md` and `docs/INTEGRATION_TEST.md`.

## CLI

```bash
python tools/publish-local-catalog/publish_local_catalog.py \
  --catalog-file data/examples/catalog-valid.ttl \
  --central-url http://localhost:8000/catalog \
  --webid https://example.org/profile/card#me \
  --token dev-token
```

The CLI sends a plain bearer token when `--token` is set. It is intended for
local/demo modes, not for strict DPoP verification.
