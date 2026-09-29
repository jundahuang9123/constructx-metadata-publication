# Solid Example Payloads

Use these files with `POST /catalog`.

The registry gate accepts only WebIDs that are present in the configured Solid
registry container (`SOLID_REGISTRY_URL`). Florian can point that environment
variable at the shared registry he wants to test.

Example:

```bash
curl -i \
  -X POST http://localhost:8000/catalog \
  -H 'Content-Type: text/turtle' \
  -H 'X-Participant-Id: https://example.org/profile/card#me' \
  --data-binary @data/examples/solid/catalog-valid.ttl
```

Expected behavior:

- registered WebID + `catalog-valid.ttl` or `catalog-valid.jsonld`: accepted and stored
- unregistered WebID + conformant catalog: rejected before SHACL validation
- registered WebID + `catalog-missing-distribution.ttl`: rejected by SHACL
- registered WebID + `catalog-invalid.ttl`: rejected by RDF parsing

