# Shared source publication API — implemented draft 0.1

This optional API receives public discovery metadata from EDC and Solid sources through the same validation and storage pipeline. One participant may have several independently updated sources. The provider-side converter/publisher reads the connector; this catalog does not need the connector's Management API credential.

This is the first functional implementation of the proposed publication contract. Its provisional profile is **not complete ConstructDCAT or DCAT-AP conformance**. Live Construct-X connector interoperability is not yet established.

## Start a local catalog

Install this repository and its development dependencies in a virtual environment:

```sh
python -m pip install -e '.[dev]'
cp config/publication-registry.example.json publication-registry.local.json
```

Generate a high-entropy publisher credential locally. Keep the token in the publisher environment or secret manager; put only its SHA-256 digest in the registry's `tokenSha256` field. This command prints a new token once and its digest:

```sh
python -c 'import hashlib,secrets; token=secrets.token_urlsafe(32); print("Token:",token); print("SHA-256:",hashlib.sha256(token.encode()).hexdigest())'
```

Replace the example identifiers and the all-zero placeholder digest in `publication-registry.local.json`. The publisher configuration's `sourceId` and root catalog IRI must match this registry. Store the token as `CATALOG_PUBLISHER_TOKEN` in the publisher's environment. Do not put the connector's Management API key here.

Run the shared API alone, without a legacy substrate mode:

```sh
unset CATALOG_MODE
export PUBLICATION_REGISTRY_FILE="$PWD/publication-registry.local.json"
export PUBLICATION_DB_PATH="$PWD/data/publications.sqlite3"
uvicorn core.app:app --host 127.0.0.1 --port 8000
```

`GET /health`, `/ready`, `/v1/profiles` and `/v1/datasets` are available. FastAPI's `/docs` provides an API view. The existing home-page UI and `/datasets` endpoint remain legacy-mode interfaces; use `/v1/datasets` for new source publications. The publisher supplies its own preview.

The shared routes are disabled when both environment variables are unset. Setting just one is a configuration error. If `CATALOG_MODE=solid` or `edc` is also set, the existing legacy routes are registered alongside the new routes. Their data is separate: the new API does not migrate or merge legacy Fuseki graphs, and the old EDC `/catalog` stub remains unchanged. Shared API-only operation needs no Fuseki service. When deploying beyond localhost, terminate TLS before accepting bearer credentials and protect the registry/database files.

## Registry contract

The complete example is [`config/publication-registry.example.json`](../config/publication-registry.example.json). All records reject unknown fields. `active` is an explicit boolean.

| Collection | Fields |
| --- | --- |
| `participants` | `id`, `active` |
| `principals` | `id`, `participantId`, `active`, `tokenSha256`, optional `identities: [{type,value}]` |
| `sources` | `id`, `participantId`, `kind` (`edc` or `solid`), `catalogIri`, `active` |
| `grants` | `principalId`, `sourceId`, `operations` (`publish` and/or `withdraw`), `active` |

Source IDs contain 1–128 letters, digits, dots, underscores or hyphens and start with a letter or digit. Catalog IRIs and record IDs must be unique; references must resolve within the file. A principal may act for another participant's source only with an explicit source grant. Source type describes the origin; it does not choose or weaken authentication.

Typed identity records can contain a DID, WebID or another administrator-established binding. **Merely storing a WebID/DID does not verify it.** This version authenticates all publishing principals with catalog-issued bearer tokens, including principals publishing Solid metadata. Native Solid-OIDC/DCP authentication adapters and verified external identity linking remain future work; the legacy Solid authentication route is not silently reused.

The registry is reread on every request. Make administration updates by atomically replacing the complete JSON file. Invalid/unreadable registry configuration fails closed with 503. Inactive participants, principals, sources or publish grants immediately hide the affected publication on the next discovery request, while preserving the stored snapshot. They also block authenticated receipt replay. Reactivation exposes the last accepted snapshot again unless it was withdrawn. Credential rotation changes the hash for the same principal; deleting/changing source or participant identities is not a migration mechanism.

## Endpoints and requests

| Request | Behavior |
| --- | --- |
| `GET /v1/profiles` | Public immutable profile identifier, exact shape bytes/hash, validation settings and size limit |
| `GET /v1/sources/{sourceId}/state` | Bearer + any active source grant; current revision including withdrawal tombstone |
| `PUT /v1/sources/{sourceId}/catalog` | Bearer + publish grant; validate then atomically replace complete snapshot |
| `DELETE /v1/sources/{sourceId}/catalog` | Bearer + withdraw grant; no body; revisioned tombstone |
| `GET /v1/sources/{sourceId}/catalog` | Public active Turtle graph or 404 |
| `GET /v1/datasets` | Public `{datasets:[...]}` with source kind/ID, participant, root catalog, revision and acceptance time |

Dataset identifiers may occur in more than one source; discovery retains their separate provenance. Public graph responses and discovery use `Cache-Control: no-store` so the API itself does not serve stale cached authorization decisions. This cannot recall metadata already downloaded by a consumer.

Mutations require `Idempotency-Key` (1–200 visible ASCII characters) and `Publication-If-Revision`. Use `none` only before first publication; use the quoted token from state, such as `"r1"`, for replacement and withdrawal. Read the baseline **before harvesting**. On 412, harvest again against current state instead of attaching a newer revision to old content. Withdrawal does not reset history: reactivation uses its tombstone revision.

An authenticated registered source without a first publication returns `404 source_unpublished`; an unknown registered-source lookup returns `404 source_not_found`. Other principals cannot obtain source state. Successful initial publication is 201; later mutations are 200. Responses include `Publication-Revision: "rN"`, `Location`, and the receipt. A replay returns the original status and receipt, even when a newer source revision now exists.

PUT takes `Content-Type: application/json` and this envelope, with actual hash and Turtle content:

```json
{
  "catalogIri": "https://example.org/catalog/constructx-edc",
  "profileIri": "urn:constructx:profile:publication-draft:0.1",
  "profileShapeHash": {"algorithm": "sha256", "value": "<64 lowercase hexadecimal characters>"},
  "audience": "public",
  "harvest": {
    "complete": true,
    "datasetCount": 2,
    "allowEmpty": false,
    "startedAt": "2026-09-29T10:00:00Z",
    "finishedAt": "2026-09-29T10:00:01Z",
    "sourceRevision": "<optional source snapshot identifier>",
    "verification": {"kind": "<optional adapter evidence>"}
  },
  "rdf": {"mediaType": "text/turtle", "content": "<complete graph>"}
}
```

The UTF-8 envelope is limited to 2 MiB, including streamed requests. Turtle is the only initial RDF serialization; JSON-LD, TriG and N-Quads are rejected. Turtle references are not dereferenced, and client-supplied shapes/imports are not executed. The server-owned profile artifact is [`core/publication/profile.ttl`](../core/publication/profile.ttl); its hash is over exact bytes, not RDF canonicalization. Do not modify this artifact under its existing version identifier.

The server independently checks envelope declarations, root binding, explicit types and reachability, stable IRIs for structural nodes, distinct reachable dataset count, and SHACL with inference disabled. Nested local catalogs and multiple distributions are supported. Other catalogs may be linked without describing them. A publication may not describe another registered source's root. Auxiliary blank nodes are allowed. A zero-dataset catalog requires both `complete: true` and `allowEmpty: true`; failed/incomplete harvests cannot erase a prior snapshot. The server cannot independently prove that the publisher fetched every connector page or that the metadata is factually correct/publication-approved.

Errors use `{accepted:false,error,detail,requestId}` with bounded field/shape diagnostics where available. Typical statuses are 400 invalid envelope/RDF, 401 invalid credential, 403 inactive member/grant, 409 profile/hash/idempotency conflict, 412 revision mismatch, 413 size limit, 415 serialization, 422 topology/SHACL/harvest failure and 428 missing revision precondition. Registry/store failures return 503. After an uncertain network/store outcome, retry the identical request and key, then reconcile `/state`.

## Storage, concurrency and limits

The new API uses one local SQLite database in WAL mode. A single `BEGIN IMMEDIATE` transaction compares the revision and writes the RDF snapshot, source state, authenticated-principal provenance and idempotency receipt together. Discovery reads accepted snapshots directly; there is no asynchronous indexing claim and no graph/metadata split across SQLite and Fuseki. This backend is suitable for the first single-host implementation; it is not a distributed multi-node storage design.

Receipts are scoped to principal, source and operation and currently retained indefinitely. The fingerprint covers method, path, revision precondition and canonicalized JSON including exact Turtle text. Canonically identical JSON is the same request; different RDF text is a different request. Authentication and current grants are checked before replay. Registry administration is file-based and evaluated per request, not transactionally coordinated with the SQLite write. Protect both stores and back up the SQLite database using a SQLite-aware procedure.

The dataset list currently scans accepted graphs; indexing, pagination, native identity adapters, registry administration UI, legacy graph migration and shared catalog UI remain future work. Domain-specific ConstructDCAT terms and SHACL requirements need agreement. No live connector or remote registry is contacted by this receiver.

## Verification

```sh
python -m pytest -q tests/test_publication_api.py
python -m pytest -q
```

Tests cover both source kinds in one catalog; one participant with independent sources; nested catalogs/multiple distributions; profile/hash/topology failures preserving prior data; wrong-source authority; revision conflicts; identical retry replay; withdrawal/reactivation; immediate discovery suspension; durable restart; concurrent writers; and rollback if receipt insertion fails after writing a candidate graph.
