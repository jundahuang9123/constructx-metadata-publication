# Solid Mode Operator Guide

Solid mode is the implemented handover path. It accepts pushed DCAT, authenticates the pusher, checks the pusher WebID against a Solid registry, validates with SHACL, stores in Fuseki, and exposes discovery APIs plus the UI.

## Quick Start

```bash
make up-solid
```

Services:

- Catalog API and UI: `http://localhost:8000`
- Fuseki Solid dataset: host port `3031`

For local development without real Solid-OIDC tokens:

```bash
SOLID_AUTH_MODE=trusted-header make up-solid
```

`trusted-header` logs a warning and trusts `X-Participant-Id`. Do not use it as proof of identity in shared or production environments.

## Registry

Point the catalog at a registry:

```bash
SOLID_REGISTRY_URL=https://solid-community-server.tmdt.info/semanticdatacatalog/public/test/ make up-solid
```

Presets:

- Test: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/test/`
- Gesundes Tal: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/stadt-wuppertal/`
- DACE: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/dace/`
- TimberConnect: `https://solid-community-server.tmdt.info/semanticdatacatalog/public/timberconnect/`

The registry structure is defined by
[`../config/solid-registry-contract.yaml`](../config/solid-registry-contract.yaml).
For editing guidance, see
[`solid-registry-contract.md`](solid-registry-contract.md).

Logs report:

- `registry_url`
- contained resource count
- resolved member count
- warnings for contained resources without configured WebID predicates

## Auth

`SOLID_AUTH_MODE=oidc` is the default. It verifies the access token signature from OIDC discovery/JWKS, extracts the `webid` claim, and verifies a DPoP proof when `SOLID_AUTH_REQUIRE_DPOP=true`.

With `SOLID_AUTH_REQUIRE_DPOP=true`, the request must include both an
`Authorization` access token and a `DPoP` proof. The token's `cnf.jkt` must match
the DPoP proof key thumbprint, and the proof must be bound to the exact
`POST /catalog` URL and method.

The sibling publisher delegates browser pushes to Inrupt's Solid `session.fetch`
when no manual token override is set. That runtime request still needs to be
captured with the publisher's `docs/auth-findings.md` procedure before the
strict OIDC path can be called secure end-to-end.

Still needing Florian confirmation:

- exact token scheme and claims issued by the Solid-OIDC setup
- whether the token always carries a `webid` claim
- whether DPoP `cnf.jkt` is present on access tokens

`SOLID_AUTH_REQUIRE_DPOP=false` accepts a valid signed token without proof of
possession. That has token replay risk and should be an explicit operational
choice, not the secure default.

`SOLID_AUTH_MODE=trusted-header` is available only as a dev fallback. It trusts
the declared WebID header and is suitable for controlled demos, not shared or
production identity proof.

## Push A Catalog

OIDC mode:

```bash
curl -i \
  -X POST http://localhost:8000/catalog \
  -H 'Authorization: DPoP <access-token>' \
  -H 'DPoP: <dpop-proof-jwt>' \
  -H 'Content-Type: text/turtle' \
  --data-binary @data/examples/solid/catalog-valid.ttl
```

Trusted-header mode:

```bash
curl -i \
  -X POST http://localhost:8000/catalog \
  -H 'Content-Type: text/turtle' \
  -H 'X-Participant-Id: https://example.org/profile/card#me' \
  --data-binary @data/examples/solid/catalog-valid.ttl
```

Responses:

- `200`: accepted
- `401`: auth failure
- `403`: authenticated WebID not registered
- `422`: RDF parse or SHACL validation failure
- `502`: Fuseki write failure

Each rejection includes `error`, `detail`, and `stage`.

## Discovery

```bash
curl http://localhost:8000/datasets
curl 'http://localhost:8000/datasets/detail?dataset_id=https%3A%2F%2Fexample.org%2Fdatasets%2Fair-quality'
```

Browse the UI at `http://localhost:8000`.

## Publisher Integration

Use the sibling publisher directory at `../publisher` for push-side testing.

Runbooks:

- Catalogue side: `docs/INTEGRATION_TEST.md`
- Publisher side: `../publisher/docs/INTEGRATION_TEST.md`
- Request-capture finding: `../publisher/docs/auth-findings.md`

Current status: trusted-header is the demo path. Strict OIDC with DPoP requires
the Phase 0 real-browser capture and a full run against a populated registry and
Fuseki before it should be described as verified end-to-end.

## Health And Readiness

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/ready` reports Fuseki and registry separately. Fuseki failure makes the app not ready. Registry failure is fail-closed for new pushes; if a cached membership list exists, pushes may use the stale cache briefly while logging a warning.

## Diagnosing

Successful push logs:

- auth success with WebID and auth mode
- registry decision
- validation success
- store graph id

Registry-format mismatch:

- contained resources found but zero members resolved
- warnings for resources that do not expose configured WebID predicates

Fuseki problem:

- `/ready` shows `fuseki=false`
- push returns `502` at stage `store`

## Publisher Repo

This service expects a participant to POST DCAT to `/catalog`. The sibling
`publisher` directory contains the current push producer for
handover testing. It reads existing Pod catalogue RDF and posts the original RDF
payload here.
