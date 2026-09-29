# Credits

## Upstream Reuse

This repository reuses selected assets from:

- Repository: `tmdt-buw/semantic-data-catalog`
- Authors: Florian Hoelken et al.
- License: Apache-2.0
- Citation: Hoelken et al., "Bridging the Discovery Gap in Solid Dataspaces with a Semantic Data Catalog", 2nd Solid Symposium, 2025.

## Derived Files

| Upstream path | Local path | Reuse type |
| --- | --- | --- |
| `backend/shapes/sdcat-shape.ttl` | `core/shared/shapes/sdcat-shape.ttl` | Copied with attribution header |
| `backend/shacl_validation.py` | `core/shared/shacl_validate.py` | Adapted to configurable shape path and `ValidationResult` |
| `backend/triplestore.py` | `core/shared/dcat_serialize.py` | Adapted `generate_dcat_dataset_ttl` helper |
| `backend/triplestore.py` | `core/shared/fuseki.py` | Adapted Fuseki named-graph write/query helpers |
| `frontend/src/solidCatalog.js` | `modes/solid/registry.py` | Reimplemented registry member reading in Python, matching `loadRegistryMembersFromContainer`: container `ldp:contains` -> member resource -> `#it`/first Thing `foaf:member` |
| `frontend/src` visual design/components | `ui/` | UI design/components adapted; data layer rewritten for this push/discovery API |
