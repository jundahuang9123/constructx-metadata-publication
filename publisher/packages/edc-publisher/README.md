# Construct-X EDC metadata publisher

A provider-side Python adapter that reads assets through the connector's **local Management API**, maps approved metadata to DCAT, validates it and publishes a complete source snapshot. It is part of the existing publisher repository. The Solid browser publisher remains available.

This implementation follows the supplied Construct-X Python library's API-key authentication and Management API configuration. It adds the asset-inventory operation missing from that library. The first query template targets the v3 asset-query interface; that route, sorting and read scope must be confirmed on the colleague's deployed build. No live Construct-X interoperability is claimed by the offline checks.

## Install

From this repository's root, with Python 3.11 or newer:

```sh
python -m venv .venv
.venv/bin/python -m pip install -e packages/edc-publisher
```

No university account or checkout is needed. The colleague's library is optional for the Python integration shown below.

## Prepare a reviewable example

```sh
.venv/bin/constructx-publisher prepare \
  --config packages/edc-publisher/examples/source.json \
  --assets-file packages/edc-publisher/examples/assets.json \
  --output output/edc-first
```

Open `output/edc-first/preview.html`. The bundle contains:

- `catalog.ttl`: the actual publication graph, with two catalogs, two datasets and three distributions in the example;
- `manifest.json`: mapping choices, omitted counts, retrieval evidence, validation results and hashes;
- `publication.json`: the proposed metadata-publication envelope;
- `preview.html`: a self-contained review page.

The example is synthetic. The asphalt record illustrates the colleague's minimal asset format, and the wall record illustrates richer approved metadata. It does not claim these records or representations are deployed. Offline file reads are labelled `offline-input-not-live-verified`.

The output directory must be new. Failed validation leaves a report but no publishable request. Failed harvesting produces no replacement. Private properties and backend addresses are never copied into the exported graph or report.

## Configure a real source

Copy `examples/source.json` and replace the provider information. Set:

- `management.baseUrl` to the provider's Management API, including `/management`; the supplied deployment defaults to `http://127.0.0.1:29110/management` on its host. A separate container needs an appropriate internal hostname.
- `management.apiKeyEnv` to the environment-variable name holding its read credential. No secrets go into source JSON, command-line arguments, bundles or version control.
- `sourceId`, `catalogIri` and `publisherIri` to the registered source and owner information. A publisher IRI is metadata, not authentication.
- `selection.assetIds` to the assets approved for publication. Alternatively, explicitly use `selection: {"allAssets": true}` if every asset is approved. Reading an asset does not itself authorize public publication.
- `approvedProperties` to the exact predicate IRIs approved for export. Mapped `name`, `description` and `contenttype` require approval of the source predicate or their destination (`dct:title`, `dct:description`, `dcat:mediaType`). Unknown properties are omitted, with a count in the report.
- `catalogs` and `assetOverrides` for provider-authored grouping, stable dataset identifiers or representation descriptions. Overrides are recorded in the mapping audit. Existing approved DCAT distribution descriptions are preserved; don't configure replacement distributions at the same time.

Domain IRIs, language tags, datatypes and approved nested JSON-LD descriptions are preserved. JSON-LD contexts must be inline or explicitly pinned as local objects in `contexts: {"context-URL": {"@context": {...}}}`. The reader never retrieves arbitrary contexts or linked data files. Compact EDC property objects and expanded JSON-LD property arrays are supported.

For a minimal asset, the mapper creates a stable dataset/distribution and links it to the configured DSP access service. The DSP URL is the entry point for governed access, not a direct download URL. It does not infer IFC/CSV representations from transfer types, fabricate domain classifications, or synthesize negotiable offers. Policy detail can be added from an authoritative source later.

## Retrieve live assets

Configure `MANAGEMENT_API_KEY` in the process environment using your deployment's secret handling. Omit `--assets-file`:

```sh
.venv/bin/constructx-publisher prepare --config source.json --output output/live-first
```

The adapter scans until an **empty** page, advancing by the rows actually returned. A short page is not assumed to be the last page. Duplicate IDs, malformed responses, paging failures and bounds abort the harvest. Two complete scans must agree by ID and content. This is evidence of observed stability, **not an atomic database snapshot**. A continually changing source needs a stronger snapshot/change-feed integration. The report states this limit.

The inventory and publication clients refuse redirects and have bounded response sizes. HTTPS should protect credentials over a network; local HTTP is supported for the supplied provider-side deployment.

## Publish to the shared receiving API

The corresponding [`catalog/`](../../../catalog/) source-publication implementation provides `/v1/profiles` and `/v1/sources/{sourceId}/...`. The old Solid `POST /catalog` endpoint is not this protocol. Configure `publication.catalogUrl`, register the source/principal/grant, and set `CATALOG_PUBLISHER_TOKEN` locally. The two credentials have different purposes.

```sh
.venv/bin/constructx-publisher prepare --with-baseline \
  --config source.json --output output/review-before-publish
# Inspect the preview, then submit the identical prepared snapshot.
.venv/bin/constructx-publisher submit --bundle output/review-before-publish
```

Or prepare and submit in one authorized operation:

```sh
.venv/bin/constructx-publisher publish --config source.json --output output/published-first
```

The publisher checks the server's profile hash and reads the source revision **before** the harvest. `request.json` records the baseline and a retry key. `receipt.json` records acceptance. If the response is lost, `submit` reuses the exact request and key; it never silently fetches a newer revision for old metadata. A conflict requires a fresh harvest. An offline `prepare` without `--with-baseline` is review-only and cannot be submitted.

```sh
.venv/bin/constructx-publisher withdraw --config source.json --output output/withdrawal
```

Withdrawal is explicit and revision checked. Empty snapshots are rejected unless source configuration explicitly sets `allowEmpty: true`.

## Use with the colleague's Python library

When that library is already installed:

```python
from python_connector_lib import ConnectorClient
from constructx_catalog_publisher.integration import inventory_from_connector
from constructx_catalog_publisher.converter import convert_assets
from constructx_catalog_publisher.validation import validate_graph

client = ConnectorClient.from_env("/path/to/connector/.env")
inventory = inventory_from_connector(client)
# source_config is the reviewed JSON configuration described above.
prepared = convert_assets(inventory.assets, source_config)
report = validate_graph(prepared.graph, source_config["catalogIri"])
```

This bridge reads `client.config.management_api` and `management_key`. It never calls lifecycle, onboarding, asset creation, contract negotiation or data-transfer methods. The supplied private library is not vendored or modified.

## Profile and current boundaries

`urn:constructx:profile:publication-draft:0.1` is a provisional, self-contained publication profile. Both validators use the same shape bytes and SHA-256. It requires titles, explicit DCAT structure and service/access links, accepts multiple distributions and nested catalogs, and rejects disconnected core resources. **It is not full ConstructDCAT or DCAT-AP conformance.** Construction anchors are preserved when supplied; missing ones currently produce a note.

The receiver initially uses administrator-configured participants, principals, sources and grants, catalog-issued tokens, and transactional SQLite storage for the new API. It is source-neutral; native Solid-OIDC/DCP integration and migration of legacy Fuseki graphs are not part of this first adapter implementation. See the catalog repository's `docs/SOURCE_PUBLICATION.md`.

## Verification

```sh
python -m pip install pytest
python -m pytest packages/edc-publisher/tests
```

Tests cover inventory completeness, mappings and exclusions, JSON-LD preservation, validation and the publication client's revision/retry behavior. The catalog repository contains independent receiving API tests. Live connector verification still requires the actual deployed version, API read access and agreed metadata.
