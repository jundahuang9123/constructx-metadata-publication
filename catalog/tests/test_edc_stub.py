from fastapi import FastAPI
from fastapi.testclient import TestClient

from modes.edc import register


def test_edc_registers_bootable_not_operational_mode() -> None:
    mode = register()

    assert mode.name == "edc"
    assert mode.discovery.get_status().mode == "edc"
    assert not mode.discovery.get_status().operational


def test_edc_push_returns_clear_not_implemented_response() -> None:
    mode = register()
    app = FastAPI()
    app.include_router(mode.ingest.routes())
    client = TestClient(app)

    response = client.post("/catalog", content="")

    assert response.status_code == 501
    assert response.json()["error"] == "edc_not_wired"
    assert response.json()["stage"] == "ingest"
