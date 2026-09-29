# Local Catalogue Publisher CLI

This tiny CLI is for smoke tests and demos. It reads a local RDF file and POSTs it to the central federated catalogue.

```bash
python tools/publish-local-catalog/publish_local_catalog.py \
  --catalog-file data/examples/catalog-valid.ttl \
  --central-url http://localhost:8000/catalog \
  --webid https://example.org/profile/card#me \
  --token dev-token
```

It exits `0` for a successful `2xx` response and non-zero otherwise.

