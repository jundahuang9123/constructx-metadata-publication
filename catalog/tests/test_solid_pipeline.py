from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.shared.shacl_validate import ShaclValidationGate
from modes.solid.auth import TrustedHeaderSolidAuth
from modes.solid.discovery import SolidDiscovery
from modes.solid.ingest import SolidIngest
from modes.solid.store import graph_uri_for_participant
from tests.fixtures import (
    FakeRegistry,
    INVALID_SHACL_TURTLE,
    MemoryCatalogStore,
    VALID_TURTLE,
    VALID_TURTLE_REPLACEMENT,
)

REGISTERED_WEBID = "https://example.org/profile/card#me"
UNREGISTERED_WEBID = "https://not.example/profile/card#me"


def _client(registry: FakeRegistry, store: MemoryCatalogStore) -> tuple[TestClient, SolidDiscovery]:
    app = FastAPI()
    validation = ShaclValidationGate()
    app.include_router(
        SolidIngest(
            registry=registry,
            validation=validation,
            store=store,
            auth=TrustedHeaderSolidAuth(),
        ).routes()
    )
    discovery = SolidDiscovery(store=store, registry=registry)
    return TestClient(app), discovery


def test_registered_conformant_push_is_stored_and_discoverable() -> None:
    store = MemoryCatalogStore()
    client, discovery = _client(FakeRegistry({REGISTERED_WEBID}), store)

    response = client.post(
        "/catalog",
        content=VALID_TURTLE,
        headers={
            "Content-Type": "text/turtle",
            "X-Participant-Id": REGISTERED_WEBID,
        },
    )

    assert response.status_code == 200
    assert response.json()["graph"] == graph_uri_for_participant(REGISTERED_WEBID)
    assert len(store.graphs) == 1
    datasets = discovery.list_datasets()
    assert len(datasets) == 1
    assert datasets[0].title == "Test dataset"
    assert datasets[0].provider == REGISTERED_WEBID
    detail = discovery.get_dataset("https://example.org/datasets/test")
    assert detail is not None
    assert detail.triples


def test_unregistered_webid_is_rejected_before_store() -> None:
    store = MemoryCatalogStore()
    client, _ = _client(FakeRegistry({REGISTERED_WEBID}), store)

    response = client.post(
        "/catalog",
        content=VALID_TURTLE,
        headers={
            "Content-Type": "text/turtle",
            "X-Participant-Id": UNREGISTERED_WEBID,
        },
    )

    assert response.status_code == 403
    assert response.json()["stage"] == "registry"
    assert response.json()["error"] == "participant_not_registered"
    assert store.graphs == {}


def test_registered_nonconformant_dcat_is_rejected_before_store() -> None:
    store = MemoryCatalogStore()
    client, _ = _client(FakeRegistry({REGISTERED_WEBID}), store)

    response = client.post(
        "/catalog",
        content=INVALID_SHACL_TURTLE,
        headers={
            "Content-Type": "text/turtle",
            "X-Participant-Id": REGISTERED_WEBID,
        },
    )

    assert response.status_code == 422
    assert response.json()["stage"] == "validation"
    assert response.json()["errors"]
    assert store.graphs == {}


def test_registered_invalid_rdf_is_rejected_before_store() -> None:
    store = MemoryCatalogStore()
    client, _ = _client(FakeRegistry({REGISTERED_WEBID}), store)

    response = client.post(
        "/catalog",
        content="this is not valid RDF",
        headers={
            "Content-Type": "text/turtle",
            "X-Participant-Id": REGISTERED_WEBID,
        },
    )

    assert response.status_code == 422
    assert response.json()["stage"] == "validation"
    assert "RDF parse error" in response.json()["errors"][0]
    assert store.graphs == {}


def test_repush_replaces_participant_graph() -> None:
    store = MemoryCatalogStore()
    client, discovery = _client(FakeRegistry({REGISTERED_WEBID}), store)
    headers = {"Content-Type": "text/turtle", "X-Participant-Id": REGISTERED_WEBID}

    first = client.post("/catalog", content=VALID_TURTLE, headers=headers)
    second = client.post("/catalog", content=VALID_TURTLE_REPLACEMENT, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(store.graphs) == 1
    datasets = discovery.list_datasets()
    assert len(datasets) == 1
    assert datasets[0].title == "Replacement dataset"
