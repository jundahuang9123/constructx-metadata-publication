# Solid Registry Contract

The editable registry contract is
[`config/solid-registry-contract.yaml`](../config/solid-registry-contract.yaml).
This Markdown file only explains how to edit it.

The default contract describes the Florian-style Solid registry shape:

```text
registry container -> member resource predicate -> member resource -> WebID predicate -> WebID
```

The currently supported `shape.type` is:

```text
ldp-container-member-resources
```

## Registry URL

The contract names the environment variable that provides the registry URL:

```yaml
registry:
  url_env: SOLID_REGISTRY_URL
```

At runtime, set `SOLID_REGISTRY_URL` to the Solid registry container URL.

## Changing Member Resource Predicates

If the registry container uses another predicate to point to participant/member
resources, add it under `shape.container.member_resource_predicates`:

```yaml
shape:
  container:
    member_resource_predicates:
      - http://www.w3.org/ns/ldp#contains
      - https://example.org/vocab#hasParticipantRecord
```

The checker will treat objects of any listed predicate as member resources.

## Changing WebID Predicates

If member resources use another predicate to list participant WebIDs, add it
under `shape.member_resource.webid_predicates`:

```yaml
shape:
  member_resource:
    webid_predicates:
      - http://xmlns.com/foaf/0.1/member
      - https://schema.org/member
```

The checker will treat objects of any listed predicate as registered WebIDs.

## WebID Matching

The default matching strategy is exact string comparison after trimming
whitespace. Fragment identifiers such as `#me` are preserved.

Do not silently change profile-document URLs into fragment WebIDs. For example,
these are different identifiers unless the project explicitly changes the
contract:

```text
https://alice.example/profile/card#me
https://alice.example/profile/card
```

If exact matching fails because of profile URL versus fragment WebID differences,
agree on the registry identity convention first, then update the YAML and tests.

## Cache And Failure Policy

The contract defines the cache TTL env var and default:

```yaml
cache:
  ttl_seconds_env: SOLID_REGISTRY_CACHE_TTL_SECONDS
  default_ttl_seconds: 300
```

The default failure policy is fail closed. If the registry or member resources
cannot be checked, publication should be rejected instead of silently allowing
the participant.

## Change Process

When changing the registry shape:

1. Edit `config/solid-registry-contract.yaml`.
2. Add or update RDF fixtures.
3. Update registry checker code only if the configured shape requires new logic.
4. Update tests proving the configured contract is followed.
