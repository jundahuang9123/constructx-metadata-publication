# Architecture

The publisher is an external client application. It does not run inside a Solid Pod.

```text
Existing Solid Pod
  catalog/cat.ttl
  catalog/ds/*.ttl
        |
        | authenticated Solid fetch
        v
Solid Publisher
        |
        | POST RDF + Solid-OIDC token
        v
Central Federated Catalogue
        |
        | registry check + SHACL validation
        v
Fuseki index + Discovery UI/API
```

The browser UI is the main product. The CLI exists for repeatable smoke tests.

## Boundaries

- The publisher reads RDF and preserves the original payload for publication.
- Preview parsing is only for operator feedback.
- The central catalogue owns registry checks, SHACL validation, persistence, and discovery.
- Florian's Solid app remains the source of Pod catalogue conventions.

