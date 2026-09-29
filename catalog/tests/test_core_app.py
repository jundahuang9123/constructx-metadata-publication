import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class _SequenceDiscovery:
    def __init__(self, statuses: list[dict[str, object]]) -> None:
        self._statuses = iter(statuses)
        self.calls = 0

    def get_status(self) -> dict[str, object]:
        self.calls += 1
        return next(self._statuses)


def _solid_status(fuseki_ready: bool, detail: str | None = None) -> dict[str, object]:
    return {
        "mode": "solid",
        "operational": fuseki_ready,
        "detail": detail,
        "dependencies": {"fuseki": fuseki_ready, "registry": True},
    }


def _load_app_module(monkeypatch):
    monkeypatch.setenv("CATALOG_MODE", "solid")
    monkeypatch.setenv("CATALOG_STARTUP_CHECKS", "false")
    import core.app as app_module

    return importlib.reload(app_module)


def test_core_app_imports_in_both_modes(monkeypatch) -> None:
    monkeypatch.setenv("CATALOG_STARTUP_CHECKS", "false")

    monkeypatch.setenv("CATALOG_MODE", "solid")
    import core.app as app_module

    app_module = importlib.reload(app_module)
    assert app_module.app.title == "Dual-Substrate Federated Catalog"

    monkeypatch.setenv("CATALOG_MODE", "edc")
    app_module = importlib.reload(app_module)
    assert app_module.app.title == "Dual-Substrate Federated Catalog"


def test_catalog_allows_local_publisher_cors_preflight(monkeypatch) -> None:
    app_module = _load_app_module(monkeypatch)
    client = TestClient(app_module.app)

    response = client.options(
        "/catalog",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-participant-id,x-participant-webid,authorization,dpop"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_startup_checks_retry_solid_fuseki_until_reachable(monkeypatch) -> None:
    app_module = _load_app_module(monkeypatch)
    monkeypatch.setenv("CATALOG_STARTUP_CHECKS", "true")
    monkeypatch.setenv("CATALOG_STARTUP_WAIT_SECONDS", "5")
    monkeypatch.setenv("CATALOG_STARTUP_RETRY_SECONDS", "0.25")

    discovery = _SequenceDiscovery(
        [
            _solid_status(False, "Solid discovery unavailable: connection refused"),
            _solid_status(True),
        ]
    )
    mode = SimpleNamespace(name="solid", discovery=discovery)
    sleeps: list[float] = []
    monotonic_values = iter([10.0, 10.0])
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(app_module.time, "sleep", sleeps.append)

    app_module._startup_checks(mode)

    assert discovery.calls == 2
    assert sleeps == [0.25]


def test_startup_checks_raise_after_solid_fuseki_wait_expires(monkeypatch) -> None:
    app_module = _load_app_module(monkeypatch)
    monkeypatch.setenv("CATALOG_STARTUP_CHECKS", "true")
    monkeypatch.setenv("CATALOG_STARTUP_WAIT_SECONDS", "0")
    monkeypatch.setenv("CATALOG_STARTUP_RETRY_SECONDS", "0.25")

    discovery = _SequenceDiscovery(
        [_solid_status(False, "Solid discovery unavailable: connection refused")]
    )
    mode = SimpleNamespace(name="solid", discovery=discovery)
    sleeps: list[float] = []
    monotonic_values = iter([10.0, 10.0])
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(app_module.time, "sleep", sleeps.append)

    with pytest.raises(RuntimeError, match="Fuseki is not reachable"):
        app_module._startup_checks(mode)

    assert discovery.calls == 1
    assert sleeps == []

