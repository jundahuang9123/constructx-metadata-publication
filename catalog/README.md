# Dual-Substrate Federated Catalog

A central, push-based federated catalog for dataspaces. Participants publish DCAT metadata to the catalog service; the service authenticates the publisher, checks membership in the configured registry, validates the RDF with SHACL, stores accepted metadata in Fuseki, and exposes discovery APIs plus a browsable UI. Solid mode is implemented for handover testing. EDC mode is present as the same structural shape, but remains a non-operational placeholder.

An opt-in **shared source publication API** now accepts metadata from both EDC and Solid through the same catalog-issued credentials, source grants, provisional SHACL profile and revisioned snapshot pipeline. It uses a durable SQLite backend so graph, revision and retry receipt commit together. It can run without either legacy mode; legacy Fuseki data is not migrated. See [the source publication quickstart and contract](docs/SOURCE_PUBLICATION.md). The remaining README describes the legacy modes.

## Architecture

```text
POST /catalog
  -> Solid auth
  -> RegistryCheck
  -> ValidationGate
  -> CatalogStore
  -> DiscoveryService
  -> UI / API consumers
```

The shared `core/` package owns interfaces, app wiring, config, and shared utilities. Mode-specific code lives under `modes/solid/` and `modes/edc/`. The import-boundary test enforces that `core/` does not import from `modes/`.

## Built On Florian Hoelken's Work

This project reuses selected Apache-2.0 assets from `tmdt-buw/semantic-data-catalog` by Florian Hoelken et al.

Citation: Hoelken et al., "Bridging the Discovery Gap in Solid Dataspaces with a Semantic Data Catalog", 2nd Solid Symposium, 2025.

| Asset | Local use | Reuse type |
| --- | --- | --- |
| DCAT SHACL profile | `core/shared/shapes/sdcat-shape.ttl` | copied with attribution header |
| SHACL validator | `core/shared/shacl_validate.py` | adapted to return `ValidationResult` |
| DCAT serializer | `core/shared/dcat_serialize.py` | adapted helper |
| Fuseki helpers | `core/shared/fuseki.py` | adapted graph-store/query helpers |
| Solid registry reader | `modes/solid/registry.py` | contract-driven membership reader for LDP registry containers and member resources |
| UI design/components | `ui/` | visual approach adapted; data layer rewritten for this push/discovery API |

See [CREDITS.md](CREDITS.md) and [NOTICE](NOTICE).

## Setup

Prerequisites:

- Docker with Compose
- Python 3.11+ for local tests

Start Solid mode:

```bash
make up-solid
```

This starts:

- Catalog API and UI: `http://localhost:8000`
- Fuseki, Solid dataset: host port `3031`

Start EDC mode:

```bash
make up-edc
```

EDC boots and reports `operational=false`; `POST /catalog` returns `501`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `CATALOG_MODE` | required by Docker service | `solid` or `edc` |
| `FUSEKI_URL` | `http://localhost:3030/solid` | Dataset URL; helpers use `/data` and `/query` under it |
| `FUSEKI_USER` | `admin` | Fuseki basic auth user |
| `FUSEKI_PASSWORD` | `admin` | Fuseki basic auth password |
| `SOLID_REGISTRY_URL` | `https://solid-community-server.tmdt.info/semanticdatacatalog/public/test/` | Solid LDP registry container |
| `SOLID_REGISTRY_CONTRACT_PATH` | `config/solid-registry-contract.yaml` | Machine-readable registry contract |
| `SOLID_REGISTRY_CACHE_TTL_SECONDS` | `300` | Registry membership cache TTL |
| `SOLID_AUTH_MODE` | `oidc` | `oidc` verifies a Solid-OIDC token; `trusted-header` trusts `X-Participant-Id` for local testing only |
| `SOLID_AUTH_REQUIRE_DPOP` | `true` | Require and verify a DPoP proof in OIDC mode |
| `SOLID_OIDC_ISSUER` | token `iss` claim | Optional fixed issuer |
| `SOLID_OIDC_AUDIENCE` | unset | Optional audience verification |
| `SOLID_DPOP_MAX_AGE_SECONDS` | `300` | DPoP proof freshness window |
| `CATALOG_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the catalog API |
| `CATALOG_STARTUP_CHECKS` | `true` | Run dependency checks on app startup |
| `CATALOG_STARTUP_WAIT_SECONDS` | `60` | Maximum time to wait for Solid Fuseki during startup checks |
| `CATALOG_STARTUP_RETRY_SECONDS` | `1` | Delay between Solid Fuseki startup-check attempts |

Registry presets from Florian's frontend:

- Test: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/test/`
- Gesundes Tal: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/stadt-wuppertal/`
- DACE: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/dace/`
- TimberConnect: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/timberconnect/`

The Solid registry structure is defined by the machine-readable contract file:

[`config/solid-registry-contract.yaml`](config/solid-registry-contract.yaml)

For editing guidance, see:

[`docs/solid-registry-contract.md`](docs/solid-registry-contract.md)

## UI

The UI is served same-origin at `http://localhost:8000`. It reads only this catalog's discovery API:

- `GET /status`
- `GET /ready`
- `GET /datasets`
- `GET /datasets/detail?dataset_id=...`

Expected screenshot path: `docs/img/ui-datasets.png`.

This environment could not run Docker/browser capture, so no fake screenshot is committed. Capture instructions are in [docs/img/README.md](docs/img/README.md). After running the app and pushing one catalog, place the real screenshot at `docs/img/ui-datasets.png`.

The screenshot should show the dataset table, provider/provenance column, search filter, operational status indicators, and the RDF graph detail panel.

## Publishing

Real mode uses Solid-OIDC:

```bash
curl -i \
  -X POST http://localhost:8000/catalog \
  -H 'Authorization: DPoP <access-token>' \
  -H 'DPoP: <dpop-proof-jwt>' \
  -H 'Content-Type: text/turtle' \
  --data-binary @data/examples/solid/catalog-valid.ttl
```

Local development can use the explicit fallback:

```bash
SOLID_AUTH_MODE=trusted-header make up-solid
```

Then push with a declared WebID:

```bash
curl -i \
  -X POST http://localhost:8000/catalog \
  -H 'Content-Type: text/turtle' \
  -H 'X-Participant-Id: https://example.org/profile/card#me' \
  --data-binary @data/examples/solid/catalog-valid.ttl
```

Expected responses:

- `200`: accepted, validated, stored in the participant graph
- `401`: auth failed, stage `auth`
- `403`: authenticated WebID is not in the Solid registry, stage `registry`
- `422`: invalid RDF or SHACL failure, stage `validation`
- `502`: Fuseki store write failed, stage `store`

Responses use:

```json
{ "error": "code", "detail": "message", "stage": "auth|registry|validation|store" }
```

## Discovering

```bash
curl http://localhost:8000/datasets
curl 'http://localhost:8000/datasets/detail?dataset_id=https%3A%2F%2Fexample.org%2Fdatasets%2Fair-quality'
```

The UI provides search/filtering, dataset details, provenance, and an RDF graph view.

## Operating

Health:

```bash
curl http://localhost:8000/health
```

Readiness:

```bash
curl http://localhost:8000/ready
```

`/ready` reports Fuseki and registry reachability separately. Startup logs dependency PASS/FAIL status. In Solid mode, startup waits up to `CATALOG_STARTUP_WAIT_SECONDS` for Fuseki before failing the app, which avoids Docker startup-order races. Registry logs include the registry URL, contained resources found, and resolved member count; a registry-format mismatch appears as zero resolved members or warnings for member resources without configured WebID predicates.

Admission control is registry-based: only authenticated WebIDs present in the configured registry may publish. Add participants by adding member resources to Florian's registry container model.

## Publisher Integration

This catalog accepts pushes. The sibling [`publisher/`](../publisher/) directory
contains the current push producers for handover testing. The Solid publisher
authenticates with Solid-OIDC, reads existing `catalog/cat.ttl` RDF
from a Pod or local file, and POSTs the original RDF payload here.

Integration runbook: [docs/INTEGRATION_TEST.md](docs/INTEGRATION_TEST.md).

Auth status:

- `trusted-header` is the local demo path and trusts the declared WebID header.
- Strict `oidc` with `SOLID_AUTH_REQUIRE_DPOP=true` requires a real
  Solid-OIDC request carrying a DPoP proof bound to `POST /catalog`.
- The publisher has a request catcher in
  [`../publisher/docs/auth-findings.md`](../publisher/docs/auth-findings.md) for that Phase 0
  diagnosis.

## Status And Limitations

- Solid mode: implemented and testable.
- EDC mode: structural placeholder only.
- UI: functional discovery UI, no Pod/Inrupt data layer.
- Needs Florian confirmation: actual token type/claims from the Solid-OIDC setup
  and a real end-to-end strict OIDC run with the publisher.
- Out of scope: HA, rate limiting, production multi-tenant hardening, `cx:` SHACL extensions.
