# Implementation notes

Date: 29 September 2026

## Purpose

This repository turns the paper concept into a first reviewable implementation. The main contribution is a provider-side EDC adapter that converts approved connector metadata into a validated DCAT publication. A shared receiving API supplies the minimum catalog-side infrastructure needed to admit, validate, version and discover publications from both EDC and Solid sources.

The work was developed from public repositories plus offline snapshots supplied by the project owner. No university account was accessed. The downloaded private Construct-X connector and Python-library snapshots are not copied into this repository.

## What was implemented

### Provider-side EDC converter/publisher

The Python package under `publisher/packages/edc-publisher` provides:

- a configurable reader for the connector's local Management API asset-query endpoint;
- bounded pagination that continues until an empty page and rejects duplicates, malformed responses and unsafe redirects;
- two matching inventory scans as evidence that the observed source did not change during collection;
- explicit asset selection and allowlisted property mapping;
- stable DCAT catalog, dataset, distribution and data-service identifiers;
- support for nested catalogs, multiple distributions, language tags, datatypes and approved domain predicates;
- local topology and SHACL validation using a packaged, versioned draft profile;
- a review bundle containing Turtle, a manifest, the exact publication request and a self-contained HTML preview;
- revision-aware publication, idempotent retry and explicit withdrawal;
- a small integration bridge that reads Management API configuration from the colleague library's existing `ConnectorClient` without vendoring or modifying that library.

The adapter does not download dataset payloads. Backend addresses, private properties and unapproved asset records are not copied into the public graph. Reading metadata with a connector credential is treated separately from permission to republish it publicly.

### Shared receiving catalog

The API under `catalog/core/publication` provides:

- one registry model for participants, publishing principals, EDC or Solid sources, typed identity bindings and source grants;
- catalog-issued bearer credentials stored as SHA-256 digests in the registry;
- an immutable profile endpoint exposing the exact SHACL artifact and hash;
- complete source snapshot publication with optimistic revision preconditions;
- independent graph, topology, root-authority and SHACL checks on the receiver;
- idempotency receipts for safe retries after uncertain outcomes;
- explicit source withdrawal with revisioned tombstones;
- atomic snapshot, revision, provenance and receipt commits in SQLite;
- public source graph retrieval and source-neutral dataset discovery for both EDC and Solid sources;
- immediate fail-closed behavior when registry records become invalid or inactive.

Each source owns one registered root catalog and one server-controlled snapshot. Nested catalogs can exist inside that source graph. One participant may register several independently updated sources. A stored DID or WebID is an administrator-established binding only; native DID/DCP and Solid-OIDC proof verification are future authentication adapters.

## Why the design is split this way

The connector remains authoritative for its asset inventory and access offers, while the publisher controls what metadata is approved for public discovery. Conversion belongs provider-side because that is where connector credentials, local mapping decisions and publication approval can be kept. The federated catalog then applies the same acceptance contract to every source and does not need the connector's Management API credential.

Local and server-side validation have different purposes. Local validation gives the provider a useful review artifact before disclosure. Server validation protects the shared catalog even if a client is outdated or misconfigured. The exact profile bytes and hash are compared so the two checks cannot silently use different shapes under the same profile identifier.

Complete source snapshots plus revisions make removals and concurrent updates explicit. A failed or incomplete harvest cannot erase the previous accepted graph, and retrying the same request cannot create another revision. This also lets an EDC source and a Solid source update independently inside one catalog.

## Verification performed

Before this public handoff, the local implementation passed:

- 54 EDC publisher tests, including inventory, mapping, exclusion, validation, CLI and receiver-integration behavior;
- 67 catalog tests, including 31 source-publication API tests;
- 9 existing Solid publisher UI tests and its production build;
- Python wheel builds for both new Python components;
- Ruff checks for new Python code and Git whitespace checks;
- an exact SHA-256 equality check for the SHACL profile packaged on both sides.

The synthetic example produces two datasets, two catalogs and three distributions. Sentinel values representing private/backend data and an unapproved asset were checked as absent from the export.

These results establish local behavior against fixtures. They do not establish live Construct-X, EDC/DSP or complete ConstructDCAT interoperability.

## Deliberate limits

- `urn:constructx:profile:publication-draft:0.1` is a small publication profile, not the final ConstructDCAT or DCAT-AP profile.
- The initial receiver uses SQLite and scans accepted graphs for discovery. Production indexing, pagination and multi-node operation remain open.
- The new `/v1` snapshot store is separate from the catalog's legacy Fuseki graphs and legacy UI.
- Both EDC and Solid sources use catalog-issued credentials on the shared API in this version.
- Two matching inventory scans show observed stability but are not an atomic connector snapshot.
- DSP catalog offers and Management API asset inventory have different views and authorization semantics; the implementation does not claim they are interchangeable.

## What needs to be confirmed with the connector colleague

1. The deployed connector build/version and its asset-query route, request body, sorting and pagination behavior.
2. The credential and network location from which the publisher may enumerate the approved inventory.
3. A sanitized representative asset response, its JSON-LD contexts and the ConstructDCAT fields that must be preserved.
4. Whether the API can provide a stable snapshot or change feed when assets change during pagination.
5. A disposable test path for asset creation, update and removal.

Secrets are not needed in shared documentation. They should be configured only in the publisher's local environment or secret manager.

## Policy and administration decisions still required

The connector owner or delegated administrator needs to approve which assets and properties may be published publicly. The federated catalog administrator needs to register the participant, publishing principal, source root and grants, then issue or rotate the publication credential. Those are governance choices represented by configuration; generating a token does not replace membership or source registration.

The domain group also needs to finalize the ConstructDCAT profile: mandatory discovery fields, construction classifications, representation semantics, supported languages and validation severity. Once agreed, the profile identifier must be versioned and both packages updated with the identical artifact.

## Next integration milestone

Run one controlled EDC source and one Solid source through the same catalog. Confirm that both appear through `/v1/datasets`, update one without changing the other, reject an unauthorized publisher and withdraw one source without deleting the other. Capture the source responses, publication manifests, validation reports and discovery results as experiment evidence.
