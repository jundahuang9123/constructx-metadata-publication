import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import DCAT, RDF, Graph

from core.publication.routes import PublicationApi
from core.publication.validation import MAX_BODY_BYTES, PROFILE_IRI

TOKEN = "test-only-long-publisher-secret"
OTHER_TOKEN = "test-only-ungranted-secret"


def registry_document():
    return {
        "participants": [{"id": "participant-a", "active": True}],
        "principals": [
            {
                "id": "publisher",
                "participantId": "participant-a",
                "active": True,
                "tokenSha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "identities": [{"type": "did", "value": "did:example:publisher"}],
            },
            {
                "id": "other",
                "participantId": "participant-a",
                "active": True,
                "tokenSha256": hashlib.sha256(OTHER_TOKEN.encode()).hexdigest(),
                "identities": [],
            },
        ],
        "sources": [
            {
                "id": source,
                "participantId": "participant-a",
                "kind": kind,
                "catalogIri": f"https://example.org/catalog/{source}",
                "active": True,
            }
            for source, kind in (("edc-a", "edc"), ("pod-a", "solid"))
        ],
        "grants": [
            {
                "principalId": "publisher",
                "sourceId": source,
                "active": True,
                "operations": ["publish", "withdraw"],
            }
            for source in ("edc-a", "pod-a")
        ],
    }


@pytest.fixture
def service(tmp_path):
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry_document()))
    api = PublicationApi(str(registry_file), str(tmp_path / "publications.sqlite3"))
    app = FastAPI()
    app.include_router(api.routes())
    with TestClient(app) as client:
        yield api, client, registry_file


def headers(revision="none", key="first", token=TOKEN):
    return {
        "Authorization": f"Bearer {token}",
        "Publication-If-Revision": revision,
        "Idempotency-Key": key,
    }


def envelope(api, source="edc-a", title="Example dataset"):
    root = f"https://example.org/catalog/{source}"
    return {
        "catalogIri": root,
        "profileIri": PROFILE_IRI,
        "profileShapeHash": api.validator.shape_hash,
        "audience": "public",
        "harvest": {
            "complete": True,
            "datasetCount": 1,
            "allowEmpty": False,
            "startedAt": "2026-09-29T09:00:00Z",
            "finishedAt": "2026-09-29T09:00:01Z",
            "sourceRevision": "test-snapshot",
            "verification": {"kind": "fixture"},
        },
        "rdf": {
            "mediaType": "text/turtle",
            "content": f'''
            @prefix dcat: <http://www.w3.org/ns/dcat#> .
            @prefix dct: <http://purl.org/dc/terms/> .
            <{root}> a dcat:Catalog; dct:title "Catalog"; dcat:catalog <{root}/nested> .
            <{root}/nested> a dcat:Catalog; dct:title "Nested"; dcat:dataset <{root}/dataset> .
            <{root}/dataset> a dcat:Dataset; dct:title "{title}";
                dcat:distribution <{root}/json>, <{root}/csv> .
            <{root}/json> a dcat:Distribution; dcat:accessURL <https://provider.example/dsp>;
                dcat:accessService <{root}/service>; dcat:mediaType "application/json" .
            <{root}/csv> a dcat:Distribution; dcat:accessURL <https://provider.example/dsp>;
                dcat:accessService <{root}/service>; dcat:mediaType "text/csv" .
            <{root}/service> a dcat:DataService; dcat:endpointURL <https://provider.example/dsp> .
        ''',
        },
    }


def put(client, body, source="edc-a", revision="none", key="first", token=TOKEN):
    return client.put(
        f"/v1/sources/{source}/catalog", json=body, headers=headers(revision, key, token)
    )


def test_publish_both_substrates_isolates_sources_and_keeps_nested_multiple_distributions(service):
    api, client, _ = service
    for source in ("edc-a", "pod-a"):
        assert put(client, envelope(api, source), source=source).status_code == 201
    assert (
        put(client, envelope(api, title="Updated"), revision='"r1"', key="second").status_code
        == 200
    )
    rows = client.get("/v1/datasets").json()["datasets"]
    assert [(row["sourceKind"], row["title"]) for row in rows] == [
        ("edc", "Updated"),
        ("solid", "Example dataset"),
    ]
    assert {row["participantId"] for row in rows} == {"participant-a"}
    rdf = client.get("/v1/sources/edc-a/catalog")
    graph = Graph().parse(data=rdf.text, format="turtle")
    assert len(set(graph.subjects(RDF.type, DCAT.Catalog))) == 2
    assert len(set(graph.subjects(RDF.type, DCAT.Distribution))) == 2
    assert rdf.headers["Publication-Revision"] == '"r2"'


def test_profiles_supplies_exact_shape_artifact(service):
    api, client, _ = service
    profile = client.get("/v1/profiles").json()["profiles"][0]
    assert profile["profileIri"] == PROFILE_IRI
    assert (
        hashlib.sha256(profile["rdf"]["content"].encode()).hexdigest()
        == profile["profileShapeHash"]["value"]
    )
    assert profile["rdf"]["content"].encode() == api.validator.shape_bytes


def test_state_distinguishes_unknown_from_unpublished(service):
    _, client, _ = service
    for source, code in (("edc-a", "source_unpublished"), ("unknown", "source_not_found")):
        result = client.get(f"/v1/sources/{source}/state", headers=headers())
        assert result.status_code == 404
        assert result.json()["error"] == code


def test_auth_and_grants_required_before_mutation(service):
    api, client, _ = service
    body = envelope(api)
    assert client.put("/v1/sources/edc-a/catalog", json=body).status_code == 401
    assert put(client, body, token="bad-token").status_code == 401
    assert put(client, body, token=OTHER_TOKEN).status_code == 403
    assert api.store.get("edc-a") is None


def test_membership_alone_does_not_grant_another_source(service):
    api, client, path = service
    document = registry_document()
    document["grants"] = [document["grants"][0]]
    path.write_text(json.dumps(document))
    assert put(client, envelope(api)).status_code == 201
    assert put(client, envelope(api, "pod-a"), source="pod-a").status_code == 403
    assert api.store.get("pod-a") is None


def test_retry_is_original_receipt_after_later_revision_and_conflicts_for_changed_body(service):
    api, client, _ = service
    first = envelope(api)
    original = put(client, first)
    assert (
        put(client, envelope(api, title="Second"), revision='"r1"', key="second").status_code == 200
    )
    replay = put(client, first)
    assert replay.status_code == original.status_code == 201
    assert replay.json() == original.json()
    assert put(client, envelope(api, title="Changed"), key="first").status_code == 409
    assert client.get("/v1/sources/edc-a/state", headers=headers()).json()["revision"] == "r2"


def test_stale_harvest_cannot_replace_latest_graph(service):
    api, client, _ = service
    assert put(client, envelope(api)).status_code == 201
    result = put(client, envelope(api, title="Stale"), key="stale")
    assert result.status_code == 412
    assert client.get("/v1/datasets").json()["datasets"][0]["title"] == "Example dataset"


@pytest.mark.parametrize(
    "fault,code",
    [
        ("missing_type", "graph_scope_invalid"),
        ("disconnected", "graph_scope_invalid"),
        ("other_root", "graph_scope_invalid"),
        ("count", "graph_scope_invalid"),
        ("shape", "profile_invalid"),
        ("incomplete", "incomplete_harvest"),
        ("hash", "profile_hash_conflict"),
        ("profile", "profile_version_conflict"),
        ("private_audience", "audience_forbidden"),
        ("jsonld", "unsupported_media_type"),
    ],
)
def test_invalid_replacement_preserves_prior_graph(service, fault, code):
    api, client, _ = service
    assert put(client, envelope(api)).status_code == 201
    body = envelope(api, title="Rejected")
    if fault == "missing_type":
        body["rdf"]["content"] = body["rdf"]["content"].replace("a dcat:DataService;", "")
    elif fault == "disconnected":
        body["rdf"]["content"] += "<urn:orphan> a dcat:Dataset ."
    elif fault == "other_root":
        body["rdf"]["content"] += '<https://example.org/catalog/pod-a> dct:title "Forbidden" .'
    elif fault == "count":
        body["harvest"]["datasetCount"] = 2
    elif fault == "shape":
        body["rdf"]["content"] = body["rdf"]["content"].replace('dct:title "Rejected";', "")
    elif fault == "incomplete":
        body["harvest"]["complete"] = False
    elif fault == "hash":
        body["profileShapeHash"] = {"algorithm": "sha256", "value": "0" * 64}
    elif fault == "profile":
        body["profileIri"] = "urn:unsupported"
    elif fault == "private_audience":
        body["audience"] = "members"
    elif fault == "jsonld":
        body["rdf"]["mediaType"] = "application/ld+json"
    rejected = put(client, body, revision='"r1"', key=fault)
    assert rejected.json()["error"] == code
    assert client.get("/v1/datasets").json()["datasets"][0]["title"] == "Example dataset"
    assert api.store.get("edc-a")[0]["revision"] == "r1"


def test_empty_needs_explicit_confirmation_and_withdrawal_retains_revision(service):
    api, client, _ = service
    body = envelope(api)
    body["rdf"]["content"] = """@prefix dcat: <http://www.w3.org/ns/dcat#> .
        @prefix dct: <http://purl.org/dc/terms/> .
        <https://example.org/catalog/edc-a> a dcat:Catalog; dct:title "Empty" ."""
    body["harvest"]["datasetCount"] = 0
    assert put(client, body).json()["error"] == "empty_not_confirmed"
    body["harvest"]["allowEmpty"] = True
    assert put(client, body).status_code == 201
    withdrawn = client.delete("/v1/sources/edc-a/catalog", headers=headers('"r1"', "withdraw"))
    assert withdrawn.status_code == 200
    assert withdrawn.json()["revision"] == "r2"
    assert client.get("/v1/sources/edc-a/catalog").status_code == 404
    assert client.get("/v1/sources/edc-a/state", headers=headers()).json()["withdrawn"] is True
    retry = client.delete("/v1/sources/edc-a/catalog", headers=headers('"r1"', "withdraw"))
    assert retry.json() == withdrawn.json()
    assert put(client, envelope(api), key="reactivate-wrong").status_code == 412
    assert put(client, envelope(api), revision='"r2"', key="reactivate").json()["revision"] == "r3"


@pytest.mark.parametrize("inactive", ["participants", "principals", "sources", "grants"])
def test_revocation_hides_discovery_and_blocks_receipt_replay(service, inactive):
    api, client, path = service
    body = envelope(api)
    assert put(client, body).status_code == 201
    document = registry_document()
    document[inactive][0]["active"] = False
    path.write_text(json.dumps(document))
    assert client.get("/v1/sources/edc-a/catalog").status_code == 404
    assert client.get("/v1/datasets").json() == {"datasets": []}
    assert put(client, body).status_code == 403


def test_concurrent_writes_against_same_revision_have_exactly_one_winner(service):
    api, client, _ = service
    assert put(client, envelope(api)).status_code == 201

    def worker(index):
        return put(
            client, envelope(api, title=f"Writer {index}"), revision='"r1"', key=f"write-{index}"
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(worker, range(4)))
    assert sorted(response.status_code for response in responses) == [200, 412, 412, 412]
    winner = next(response for response in responses if response.status_code == 200)
    assert api.store.get("edc-a")[0]["revision"] == winner.json()["revision"] == "r2"


def test_database_failure_rolls_back_graph_revision_and_receipt(service, monkeypatch):
    api, client, _ = service
    assert put(client, envelope(api)).status_code == 201
    original_connect = api.store._connect

    class FailReceipt:
        def __init__(self, inner):
            self.inner = inner

        def execute(self, query, *args):
            if query.startswith("INSERT INTO receipts"):
                raise sqlite3.OperationalError("simulated receipt failure")
            return self.inner.execute(query, *args)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def __enter__(self):
            self.inner.__enter__()
            return self

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

    monkeypatch.setattr(api.store, "_connect", lambda: FailReceipt(original_connect()))
    result = put(client, envelope(api, title="Must roll back"), revision='"r1"', key="failed")
    assert result.status_code == 503
    monkeypatch.setattr(api.store, "_connect", original_connect)
    assert api.store.get("edc-a")[0]["revision"] == "r1"
    assert client.get("/v1/datasets").json()["datasets"][0]["title"] == "Example dataset"
    assert (
        put(
            client, envelope(api, title="Must roll back"), revision='"r1"', key="failed"
        ).status_code
        == 200
    )


def test_request_limit_precondition_and_media_type(service):
    api, client, _ = service
    result = client.put(
        "/v1/sources/edc-a/catalog",
        json=envelope(api),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert result.status_code == 428
    result = client.put(
        "/v1/sources/edc-a/catalog",
        content="x" * (MAX_BODY_BYTES + 1),
        headers={**headers(), "Content-Type": "application/json"},
    )
    assert result.status_code == 413
    result = client.put("/v1/sources/edc-a/catalog", content="Turtle", headers=headers())
    assert result.status_code == 415


def test_external_catalog_reference_and_auxiliary_blank_node_are_allowed(service):
    api, client, _ = service
    body = envelope(api)
    body["rdf"]["content"] += """
       <https://example.org/catalog/edc-a> dcat:catalog <https://external.example/catalog>;
          dct:publisher [ <http://xmlns.com/foaf/0.1/name> "Example participant" ] ."""
    assert put(client, body).status_code == 201


@pytest.mark.parametrize("body", ['{"x":1,"x":2}', '{"x":NaN}'])
def test_ambiguous_or_nonstandard_json_is_rejected(service, body):
    _, client, _ = service
    result = client.put(
        "/v1/sources/edc-a/catalog",
        content=body,
        headers={**headers(), "Content-Type": "application/json"},
    )
    assert result.status_code == 400
    assert result.json()["error"] == "invalid_envelope"


def test_deep_json_is_rejected_without_server_error(service):
    _, client, _ = service
    body = '{"deep":' + "[" * 1500 + "0" + "]" * 1500 + "}"
    result = client.put(
        "/v1/sources/edc-a/catalog",
        content=body,
        headers={**headers(), "Content-Type": "application/json"},
    )
    assert result.status_code == 400
    assert result.json()["error"] == "invalid_envelope"


def test_restart_recovers_publication_and_receipt(service):
    api, client, path = service
    body = envelope(api)
    receipt = put(client, body).json()
    restarted = PublicationApi(str(path), api.store.path)
    app = FastAPI()
    app.include_router(restarted.routes())
    with TestClient(app) as new_client:
        assert new_client.get("/v1/datasets").json()["datasets"][0]["revision"] == "r1"
        assert put(new_client, body).json() == receipt


def test_shared_routes_work_without_legacy_mode(service, monkeypatch):
    api, _, path = service
    monkeypatch.delenv("CATALOG_MODE", raising=False)
    monkeypatch.setenv("PUBLICATION_REGISTRY_FILE", str(path))
    monkeypatch.setenv("PUBLICATION_DB_PATH", api.store.path)
    from core.app import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").json()["mode"] == "shared"
        assert client.get("/ready").json()["ready"] is True
        assert put(client, envelope(api)).status_code == 201
