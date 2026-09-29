import pytest

from core.config import load_active_mode


@pytest.mark.parametrize(("mode", "expected"), [("solid", "solid"), ("edc", "edc")])
def test_mode_switch_loads_registration(monkeypatch: pytest.MonkeyPatch, mode: str, expected: str) -> None:
    monkeypatch.setenv("CATALOG_MODE", mode)

    assert load_active_mode().name == expected


def test_mode_switch_rejects_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOG_MODE", "invalid")

    with pytest.raises(RuntimeError):
        load_active_mode()

