# Federated Catalogue Publisher

## What This Is

This repository contains the existing Solid browser publisher and a provider-side Construct-X EDC converter/publisher. The EDC adapter reads an authorized asset inventory, maps approved metadata into DCAT, validates it and publishes a source-scoped snapshot. See [the EDC publisher guide](packages/edc-publisher/README.md) for installation, offline preparation and live integration.

The Solid browser application reads an existing catalogue from a Pod, previews the RDF and publishes the original graph through its existing integration. Its authentication and endpoint behavior are separate from the new shared source API.

## What This Is Not

- This is not a Solid Pod server.
- This is not a replacement for Florian Hoelken et al.'s `semantic-data-catalog`.
- This does not install code into a Pod.
- This does not replace the central federated catalogue.
- The EDC adapter is implemented against a configurable Management API query; live compatibility with the colleague's Construct-X build remains to be verified.

## EDC adapter

The [Python package](packages/edc-publisher/README.md) provides paginated asset reading, explicit property selection, catalog assembly, local SHACL validation, review bundles, revision-aware publication and withdrawal. The [provisional profile](packages/edc-publisher/src/constructx_catalog_publisher/profile.ttl) is not a complete ConstructDCAT/DCAT-AP profile. Connector credentials stay in the provider-side process.

The following sections document the existing Solid browser application.

## Architecture

```text
Existing Solid Pod
  catalog/cat.ttl
  catalog/ds/*.ttl
        |
        | authenticated Solid fetch
        v
Solid Publisher
        |
        | POST RDF via Solid session fetch
        v
Central Federated Catalogue
        |
        | registry check + SHACL validation
        v
Fuseki index
        |
        v
Discovery API/UI
```

## Relation To Florian's Semantic Data Catalog

This publisher builds on the Solid catalogue conventions and selected implementation ideas from Florian Hoelken et al.'s `semantic-data-catalog`.

Adapted ideas include Solid-OIDC session handling, catalogue path conventions, WebID conventions, DCAT modelling choices, and UI concepts. The central publishing workflow is new: it adds a participant-side push step from a Solid catalogue to a central federated catalogue.

Credit:

- Florian Hoelken et al., Semantic Data Catalog for decentralized Solid-based dataspaces
- TMDT / University of Wuppertal
- Repository: `https://github.com/tmdt-buw/semantic-data-catalog`
- License: Apache-2.0

## How It Works

1. Log in with Solid-OIDC.
2. Select a catalogue by URL, WebID-based convention, or local file.
3. Preview the RDF and DCAT counts.
4. Publish the original RDF payload to the central catalogue.
5. Inspect the central catalogue response.

## Quick Start

```bash
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

With Docker:

```bash
docker compose up --build
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_DEFAULT_IDP` | `https://solidcommunity.net` | Default Solid identity provider shown in the UI |
| `VITE_CENTRAL_CATALOG_URL` | `http://localhost:8000/catalog` | Default central catalogue publish endpoint |

## Running With An Existing Solid Setup

The publisher is external to the Pod. It authenticates as a WebID and fetches existing catalogue RDF. A direct catalogue URL should usually look like:

```text
https://<pod-host>/<user>/catalog/cat.ttl
```

For WebID-based resolution, the app infers:

```text
<pod-root>/catalog/cat.ttl
```

If the Pod layout differs, use the explicit catalogue URL.

## Publishing A Catalogue

For strict Solid-OIDC catalogues, leave the access-token override empty and let
the authenticated Solid `session.fetch` make the `POST`. That path sets the RDF
and participant headers, while the Solid client decides whether and how to attach
`Authorization` and `DPoP`:

```http
POST /catalog
Content-Type: text/turtle
X-Participant-WebID: <authenticated WebID>
X-Participant-Id: <authenticated WebID>
```

Whether Inrupt's `session.fetch` attaches a DPoP-bound request for the central
catalogue URL must be verified with `docs/auth-findings.md` before calling the
strict OIDC path secure end-to-end.

The access-token override field sends a plain `Authorization: Bearer <token>`.
Use it for local development or catalogue modes that do not require DPoP. Do not
treat it as compatible with a strict DPoP-validating OIDC catalogue.

Local file upload can preview without login, but the central catalogue may still
require authentication for publishing.

## Auth Compatibility

| Catalogue mode | Publisher path | Status |
| --- | --- | --- |
| `SOLID_AUTH_MODE=trusted-header` | WebID headers, optional manual bearer override | Demo/local only |
| `SOLID_AUTH_MODE=oidc`, `SOLID_AUTH_REQUIRE_DPOP=true` | Real Solid login, no token override, delegated `session.fetch` | Requires Phase 0 capture and end-to-end verification |
| Manual token override | Plain `Authorization: Bearer` | Not proof-of-possession |

See [docs/auth-findings.md](docs/auth-findings.md) and
[docs/INTEGRATION_TEST.md](docs/INTEGRATION_TEST.md).

## Using The CLI Publisher

```bash
python tools/publish-local-catalog/publish_local_catalog.py \
  --catalog-file data/examples/catalog-valid.ttl \
  --central-url http://localhost:8000/catalog \
  --webid https://example.org/profile/card#me \
  --token dev-token
```

The CLI exits `0` for a `2xx` central catalogue response and non-zero otherwise.
It sends the same plain bearer override as the UI. Use it for trusted-header or
non-DPoP development modes, not for the strict DPoP path.

## Expected Central Catalogue Behavior

- `200`: publication accepted
- `401`: Solid login token missing, expired, or rejected
- `403`: WebID is not registered in the central catalogue's Solid registry
- `422`: RDF failed DCAT/SHACL validation
- network error: central catalogue could not be reached

## Screenshots

Place screenshots under `docs/screenshots/`. The UI is a single-page operator tool with login, source selection, RDF preview, publish controls, and result panels.

## Troubleshooting

- If login does not return a WebID, confirm the identity provider and redirect URL.
- If catalogue fetch fails, try the direct `catalog/cat.ttl` URL and confirm public/authenticated read access.
- If preview shows no datasets, confirm the RDF uses `dcat:Dataset`.
- If publishing is rejected, inspect the central catalogue response body; it should name `auth`, `registry`, `validation`, or `store`.

## Development

```bash
npm install
npm run dev
npm run test
npm run build
```

## Credits

See [CREDITS.md](CREDITS.md) and [NOTICE](NOTICE).
