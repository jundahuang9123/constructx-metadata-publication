from pathlib import Path


def test_ui_uses_discovery_api_not_pod_data_layer() -> None:
    ui_text = "\n".join(path.read_text() for path in Path("ui").glob("*.*"))

    assert "/datasets" in ui_text
    assert "/status" in ui_text
    assert "@inrupt" not in ui_text
    assert "solidCatalog" not in ui_text

