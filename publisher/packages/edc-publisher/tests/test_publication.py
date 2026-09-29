"""Publication protocol and optional receiver integration, entirely without sockets.

Set CATALOG_SOURCE_PATH to a checkout containing core/publication/routes.py to run
the cross-repository cases. A TestClient-backed urllib opener passes actual
request bytes and headers to the real receiver routes, registry and SQLite store.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest

from constructx_catalog_publisher import cli
from constructx_catalog_publisher.converter import EDC, PROFILE_IRI
from constructx_catalog_publisher.inventory import InventorySnapshot
from constructx_catalog_publisher.publication import PublicationClient, PublicationError
from constructx_catalog_publisher.validation import profile_hash

TOKEN = "test-only-publisher-token"
SOURCE = "edc-a"
ROOT = "https://example.org/catalog/edc-a"


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit):
        return self.body[:limit]


class StubOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        status, body = next(self.responses)
        if status >= 400:
            raise HTTPError(
                request.full_url, status, "test response", {}, io.BytesIO(json.dumps(body).encode())
            )
        return Response(status, body)


def profiles():
    return {"profiles": [{"profileIri": PROFILE_IRI, "profileShapeHash": profile_hash()}]}


def configuration():
    return {
        "sourceId": SOURCE,
        "catalogIri": ROOT,
        "title": "EDC source catalog",
        "publisherIri": "https://example.org/participant",
        "dspEndpoint": "https://example.org/connector/dsp/2025-1",
        "selection": {"allAssets": True},
        "approvedProperties": [EDC + "name", EDC + "contenttype"],
        "publication": {"catalogUrl": "http://testserver", "tokenEnv": "CATALOG_PUBLISHER_TOKEN"},
    }


def assets(title="Synthetic asphalt metadata"):
    return [{"@id": "asset-a", "properties": {"name": title, "contenttype": "application/json"}}]


def snapshot(records=None):
    records = assets() if records is None else records
    return InventorySnapshot(
        records,
        "2026-09-29T09:00:00Z",
        "2026-09-29T09:00:01Z",
        hashlib.sha256(cli.encode(records)).hexdigest(),
        4,
        "two-matching-scans",
    )


def test_baseline_requires_exact_profile_hash_before_reading_state():
    unsupported = profiles()
    unsupported["profiles"][0]["profileShapeHash"]["value"] = "0" * 64
    client = PublicationClient("http://testserver", TOKEN)
    opener = StubOpener([(200, unsupported)])
    client._opener = opener
    with pytest.raises(PublicationError, match="exact provisional profile"):
        client.baseline(SOURCE, ROOT)
    assert [urlsplit(r.full_url).path for r in opener.requests] == ["/v1/profiles"]


@pytest.mark.parametrize(
    "state, expected",
    [
        ((404, {"error": "source_unpublished"}), "none"),
        ((200, {"catalogIri": ROOT, "revision": "r7"}), '"r7"'),
    ],
)
def test_baseline_reads_authorized_source_state(state, expected):
    client = PublicationClient("http://testserver", TOKEN)
    opener = StubOpener([(200, profiles()), state])
    client._opener = opener
    assert client.baseline(SOURCE, ROOT) == expected
    assert opener.requests[-1].get_header("Authorization") == "Bearer " + TOKEN


def test_publication_sends_exact_payload_and_saved_concurrency_headers():
    client = PublicationClient("http://testserver", TOKEN)
    opener = StubOpener([(201, {"accepted": True, "revision": "r1"})])
    client._opener = opener
    payload = b'{"purpose":"exact saved bytes"}\n'
    result = client.submit(SOURCE, payload, "none", "saved-request-key")
    request = opener.requests[0]
    assert request.data == payload
    assert request.get_method() == "PUT"
    assert request.get_header("Publication-if-revision") == "none"
    assert request.get_header("Idempotency-key") == "saved-request-key"
    assert result["revision"] == "r1"


def test_changed_prepared_payload_is_rejected_before_any_network_or_token_lookup(
    tmp_path, monkeypatch
):
    original = cli.encode({"rdf": "reviewed bytes"})
    (tmp_path / "request.json").write_bytes(
        cli.encode(
            {
                "method": "PUT",
                "payloadSha256": hashlib.sha256(original).hexdigest(),
                "catalogUrl": "http://testserver",
                "sourceId": SOURCE,
                "baselineRevision": "none",
                "idempotencyKey": "original-key",
            }
        )
    )
    (tmp_path / "publication.json").write_bytes(original + b" ")
    monkeypatch.delenv("CATALOG_PUBLISHER_TOKEN", raising=False)

    def forbidden(*_):
        raise AssertionError("Changed payload must be rejected before constructing a client")

    monkeypatch.setattr(cli, "PublicationClient", forbidden)
    with pytest.raises(ValueError, match="Prepared payload changed"):
        cli.submit(tmp_path, "CATALOG_PUBLISHER_TOKEN")
    assert not (tmp_path / "receipt.json").exists()


def test_offline_prepare_without_baseline_cannot_be_submitted(tmp_path, monkeypatch):
    config_path, assets_path = tmp_path / "source.json", tmp_path / "assets.json"
    config_path.write_bytes(cli.encode(configuration()))
    assets_path.write_bytes(cli.encode(assets()))
    bundle = tmp_path / "offline-bundle"

    def forbidden(*_):
        raise AssertionError("Offline preparation must not construct a publication client")

    monkeypatch.setattr(cli, "PublicationClient", forbidden)
    assert (
        cli.main(
            [
                "prepare",
                "--config",
                str(config_path),
                "--assets-file",
                str(assets_path),
                "--output",
                str(bundle),
            ]
        )
        == 0
    )
    assert (bundle / "publication.json").exists()
    assert not (bundle / "request.json").exists()
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["baselineRevision"] is None
    assert manifest["harvest"]["verification"]["live"] is False
    assert manifest["harvest"]["verification"]["method"] == "offline-input-not-live-verified"
    assert cli.main(["submit", "--bundle", str(bundle)]) == 1
    assert not (bundle / "receipt.json").exists()


class ReceiverOpener:
    """Bridge urllib's Request into an actual in-process ASGI receiver."""

    def __init__(self, receiver, events):
        self.receiver = receiver
        self.events = events

    def open(self, request, timeout):
        path = urlsplit(request.full_url).path
        self.events.append((request.get_method(), path, request.data, dict(request.header_items())))
        response = self.receiver.request(
            request.get_method(),
            path,
            content=request.data,
            headers=dict(request.header_items()),
            follow_redirects=False,
        )
        if response.status_code >= 400:
            raise HTTPError(
                request.full_url,
                response.status_code,
                "receiver response",
                response.headers,
                io.BytesIO(response.content),
            )
        return Response(response.status_code, response.content)


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    checkout = os.environ.get("CATALOG_SOURCE_PATH")
    if not checkout:
        pytest.skip("Set CATALOG_SOURCE_PATH to run actual receiver integration")
    checkout = str(Path(checkout).resolve())
    if not (Path(checkout) / "core/publication/routes.py").is_file():
        pytest.fail("CATALOG_SOURCE_PATH does not contain the source publication receiver")
    monkeypatch.syspath_prepend(checkout)
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from core.publication.routes import PublicationApi

    registry = {
        "participants": [{"id": "participant", "active": True}],
        "principals": [
            {
                "id": "publisher",
                "participantId": "participant",
                "active": True,
                "tokenSha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "identities": [],
            }
        ],
        "sources": [
            {
                "id": SOURCE,
                "participantId": "participant",
                "kind": "edc",
                "catalogIri": ROOT,
                "active": True,
            }
        ],
        "grants": [
            {
                "principalId": "publisher",
                "sourceId": SOURCE,
                "operations": ["publish", "withdraw"],
                "active": True,
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry))
    api = PublicationApi(str(registry_path), str(tmp_path / "receiver.sqlite3"))
    app = fastapi.FastAPI()
    app.include_router(api.routes())
    events = []
    with testclient.TestClient(app) as http:
        opener = ReceiverOpener(http, events)
        monkeypatch.setattr(
            "constructx_catalog_publisher.publication.build_opener", lambda *_: opener
        )
        monkeypatch.setenv("CATALOG_PUBLISHER_TOKEN", TOKEN)
        yield api, http, events


def save_config(tmp_path, name="source"):
    path = tmp_path / (name + ".json")
    path.write_bytes(cli.encode(configuration()))
    return path


def test_prepare_captures_actual_receiver_baseline_before_inventory(
    receiver, tmp_path, monkeypatch
):
    _, _, events = receiver

    def harvest(*_):
        events.append(("INVENTORY", "", None, {}))
        return snapshot()

    monkeypatch.setattr(cli, "inventory", harvest)
    source = save_config(tmp_path)
    bundle = tmp_path / "prepared"
    assert (
        cli.main(["prepare", "--with-baseline", "--config", str(source), "--output", str(bundle)])
        == 0
    )
    assert [(event[0], event[1]) for event in events] == [
        ("GET", "/v1/profiles"),
        ("GET", f"/v1/sources/{SOURCE}/state"),
        ("INVENTORY", ""),
    ]
    saved = json.loads((bundle / "request.json").read_text())
    assert saved["baselineRevision"] == "none"
    assert (
        saved["payloadSha256"]
        == hashlib.sha256((bundle / "publication.json").read_bytes()).hexdigest()
    )
    assert not (bundle / "receipt.json").exists()


def test_cli_publishes_actual_metadata_and_identical_retry_preserves_receipt(
    receiver, tmp_path, monkeypatch
):
    api, http, events = receiver
    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot())
    source = save_config(tmp_path)
    bundle = tmp_path / "published"
    assert cli.main(["publish", "--config", str(source), "--output", str(bundle)]) == 0
    first_receipt = (bundle / "receipt.json").read_bytes()
    assert json.loads(first_receipt)["revision"] == "r1"
    rows = http.get("/v1/datasets").json()["datasets"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Synthetic asphalt metadata"
    assert rows[0]["sourceKind"] == "edc"
    events.clear()
    assert cli.main(["submit", "--bundle", str(bundle)]) == 0
    assert (bundle / "receipt.json").read_bytes() == first_receipt
    assert api.store.get(SOURCE)[0]["revision"] == "r1"
    assert [(event[0], event[1]) for event in events] == [("PUT", f"/v1/sources/{SOURCE}/catalog")]


def test_stale_prepared_bundle_is_rejected_without_rebasing(receiver, tmp_path, monkeypatch):
    api, http, events = receiver
    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot())
    source = save_config(tmp_path)
    stale, first = tmp_path / "stale", tmp_path / "first"
    assert (
        cli.main(["prepare", "--with-baseline", "--config", str(source), "--output", str(stale)])
        == 0
    )
    stale_request = (stale / "request.json").read_bytes()
    assert cli.main(["publish", "--config", str(source), "--output", str(first)]) == 0
    events.clear()
    assert cli.main(["submit", "--bundle", str(stale)]) == 1
    assert [(event[0], event[1]) for event in events] == [("PUT", f"/v1/sources/{SOURCE}/catalog")]
    assert (stale / "request.json").read_bytes() == stale_request
    assert not (stale / "receipt.json").exists()
    assert api.store.get(SOURCE)[0]["revision"] == "r1"
    assert http.get("/v1/datasets").json()["datasets"][0]["title"] == "Synthetic asphalt metadata"


def test_retry_after_later_publication_returns_original_receipt_without_rollback(
    receiver, tmp_path, monkeypatch
):
    api, http, _ = receiver
    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot())
    source = save_config(tmp_path)
    first, second = tmp_path / "first", tmp_path / "second"
    assert cli.main(["publish", "--config", str(source), "--output", str(first)]) == 0
    first_receipt = (first / "receipt.json").read_bytes()
    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot(assets("Updated metadata")))
    assert cli.main(["publish", "--config", str(source), "--output", str(second)]) == 0
    assert cli.main(["submit", "--bundle", str(first)]) == 0
    assert (first / "receipt.json").read_bytes() == first_receipt
    assert api.store.get(SOURCE)[0]["revision"] == "r2"
    assert http.get("/v1/datasets").json()["datasets"][0]["title"] == "Updated metadata"


def test_cli_withdraw_saved_delete_retry_and_reactivation(receiver, tmp_path, monkeypatch):
    api, http, events = receiver
    source = save_config(tmp_path)
    published = tmp_path / "published"
    withdrawn = tmp_path / "withdrawn"
    reactivated = tmp_path / "reactivated"
    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot())
    assert cli.main(["publish", "--config", str(source), "--output", str(published)]) == 0

    def forbidden_inventory(*_):
        raise AssertionError("Withdrawal must not read the connector inventory")

    monkeypatch.setattr(cli, "inventory", forbidden_inventory)
    events.clear()
    assert cli.main(["withdraw", "--config", str(source), "--output", str(withdrawn)]) == 0
    assert [(event[0], event[1]) for event in events] == [
        ("GET", "/v1/profiles"),
        ("GET", f"/v1/sources/{SOURCE}/state"),
        ("DELETE", f"/v1/sources/{SOURCE}/catalog"),
    ]
    saved_request = json.loads((withdrawn / "request.json").read_text())
    assert saved_request["method"] == "DELETE"
    assert saved_request["baselineRevision"] == '"r1"'
    assert saved_request["payloadSha256"] == hashlib.sha256(b"").hexdigest()
    assert events[-1][2] is None
    assert not (withdrawn / "publication.json").exists()
    first_receipt = (withdrawn / "receipt.json").read_bytes()
    assert json.loads(first_receipt)["revision"] == "r2"
    assert json.loads(first_receipt)["withdrawn"] is True
    assert api.store.get(SOURCE)[1] is None
    assert http.get(f"/v1/sources/{SOURCE}/catalog").status_code == 404
    assert http.get("/v1/datasets").json()["datasets"] == []

    events.clear()
    assert cli.main(["submit", "--bundle", str(withdrawn)]) == 0
    assert [(event[0], event[1]) for event in events] == [
        ("DELETE", f"/v1/sources/{SOURCE}/catalog")
    ]
    assert events[0][2] is None
    assert events[0][3]["Idempotency-key"] == saved_request["idempotencyKey"]
    assert events[0][3]["Publication-if-revision"] == '"r1"'
    assert (withdrawn / "receipt.json").read_bytes() == first_receipt
    assert api.store.get(SOURCE)[0]["revision"] == "r2"

    monkeypatch.setattr(cli, "inventory", lambda *_: snapshot(assets("Reactivated metadata")))
    assert cli.main(["publish", "--config", str(source), "--output", str(reactivated)]) == 0
    replacement_request = json.loads((reactivated / "request.json").read_text())
    assert replacement_request["baselineRevision"] == '"r2"'
    assert api.store.get(SOURCE)[0]["revision"] == "r3"
    assert api.store.get(SOURCE)[0]["withdrawn"] is False
    assert http.get("/v1/datasets").json()["datasets"][0]["title"] == "Reactivated metadata"

    # A delayed retry acknowledges the original withdrawal without deleting r3.
    assert cli.main(["submit", "--bundle", str(withdrawn)]) == 0
    assert (withdrawn / "receipt.json").read_bytes() == first_receipt
    assert api.store.get(SOURCE)[0]["revision"] == "r3"
    assert http.get(f"/v1/sources/{SOURCE}/catalog").status_code == 200


def test_actual_receiver_profile_mismatch_stops_before_inventory(receiver, tmp_path, monkeypatch):
    api, _, events = receiver
    api.validator.shape_hash = {"algorithm": "sha256", "value": "0" * 64}

    def forbidden(*_):
        raise AssertionError("Inventory must not run for an unsupported receiver profile")

    monkeypatch.setattr(cli, "inventory", forbidden)
    source = save_config(tmp_path)
    assert (
        cli.main(["publish", "--config", str(source), "--output", str(tmp_path / "bad-profile")])
        == 1
    )
    assert [(event[0], event[1]) for event in events] == [("GET", "/v1/profiles")]
    assert api.store.get(SOURCE) is None


def test_invalid_local_metadata_writes_review_report_without_sending_put(
    receiver, tmp_path, monkeypatch
):
    api, _, events = receiver
    monkeypatch.setattr(
        cli,
        "inventory",
        lambda *_: snapshot(
            [{"@id": "untitled", "properties": {"contenttype": "application/json"}}]
        ),
    )
    source = save_config(tmp_path)
    bundle = tmp_path / "invalid"
    assert cli.main(["publish", "--config", str(source), "--output", str(bundle)]) == 1
    assert (bundle / "preview.html").is_file()
    assert json.loads((bundle / "manifest.json").read_text())["validation"]["conforms"] is False
    assert not (bundle / "request.json").exists()
    assert not (bundle / "publication.json").exists()
    assert not any(event[0] == "PUT" for event in events)
    assert api.store.get(SOURCE) is None
