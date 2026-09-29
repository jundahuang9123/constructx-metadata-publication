# Construct-X Metadata Publication

An experimental provider-side pipeline for publishing discoverable DCAT metadata from Eclipse Dataspace Components (EDC) into one federated catalog that can also receive Solid metadata.

The main contribution is the EDC converter/publisher. It reads the inventory visible through an authorized connector Management API, selects explicitly approved metadata, converts it into a DCAT catalog, validates the result locally and publishes a complete source-scoped snapshot. The receiving catalog checks identity and grants, validates the graph again and stores an atomic revision for shared discovery.

## Architecture

```text
EDC Management API                         Existing Solid catalog
        |                                          |
        v                                          v
EDC inventory adapter                      Solid publisher UI
        |                                          |
        v                                          |
approved mapping -> DCAT -> local SHACL            |
        |                                          |
        +--------------- publish -----------------+
                            |
                            v
                 Shared source publication API
             registry -> auth/grant -> SHACL -> store
                            |
                            v
                  source-neutral discovery API
```

The source registry can describe both EDC and Solid sources. Its identity records may hold DIDs, WebIDs or other administrator-established identifiers. The implemented shared API currently authenticates publishing clients with catalog-issued bearer credentials; storing an identity binding does not itself verify that external identity.

## Repository layout

| Path | Role |
| --- | --- |
| [`publisher/`](publisher/) | Existing Solid browser publisher plus the new provider-side Python EDC converter/publisher |
| [`publisher/packages/edc-publisher/`](publisher/packages/edc-publisher/) | Main EDC contribution: inventory retrieval, mapping, DCAT assembly, validation, review bundle and publication client |
| [`catalog/`](catalog/) | Dual-substrate federated catalog and the new shared source publication API |
| [`catalog/docs/SOURCE_PUBLICATION.md`](catalog/docs/SOURCE_PUBLICATION.md) | Registry, API, revision, validation and storage contract |
| [`IMPLEMENTATION_NOTES.md`](IMPLEMENTATION_NOTES.md) | What was implemented, why, verification evidence and remaining integration work |

## Quick local check

The Python components require Python 3.11 or newer.

```sh
python -m venv .venv
.venv/bin/python -m pip install -e 'catalog[dev]'
.venv/bin/python -m pip install -e publisher/packages/edc-publisher pytest
(cd catalog && ../.venv/bin/python -m pytest -q)
(cd publisher/packages/edc-publisher && \
  CATALOG_SOURCE_PATH="$PWD/../../../catalog" ../../../.venv/bin/python -m pytest -q)
```

Prepare the synthetic review bundle without contacting a connector:

```sh
.venv/bin/constructx-publisher prepare \
  --config publisher/packages/edc-publisher/examples/source.json \
  --assets-file publisher/packages/edc-publisher/examples/assets.json \
  --output output/edc-first
```

Then open `output/edc-first/preview.html`. For a live connector and publication setup, follow the [publisher guide](publisher/packages/edc-publisher/README.md) and [receiver guide](catalog/docs/SOURCE_PUBLICATION.md).

## Current status

The fixture-backed converter, publisher client and shared receiving API are implemented and covered by local tests. The included profile, `urn:constructx:profile:publication-draft:0.1`, is deliberately provisional. It is not complete ConstructDCAT or DCAT-AP conformance.

Live compatibility still requires confirmation against the deployed Construct-X connector: its exact Management API query behavior, read scope, pagination, JSON-LD contexts and representative metadata. Publication scope and registry records also need approval from the relevant connector/catalog administrators. Connector credentials remain local to the provider-side publisher and are never sent to the federated catalog.

The downloaded private Construct-X connector/library snapshots used for offline analysis are not included in this repository.

## License and attribution

The two components are licensed under Apache License 2.0. Their `NOTICE` and `CREDITS.md` files retain component-specific attribution, including reused work from Florian Hoelken and the TMDT semantic data catalog project.
