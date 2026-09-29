from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("publish_local_catalog.py")
SPEC = importlib.util.spec_from_file_location("publish_local_catalog", MODULE_PATH)
assert SPEC is not None
publish_local_catalog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publish_local_catalog)


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"accepted": true}'


class PublishLocalCatalogTest(TestCase):
    def test_sends_both_participant_headers(self) -> None:
        webid = "https://pod.example/alice/profile/card#me"
        captured = {}

        def fake_urlopen(request: object, timeout: int) -> FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "catalog.ttl"
            catalog_path.write_text(
                "@prefix dcat: <http://www.w3.org/ns/dcat#> .",
                encoding="utf-8",
            )
            argv = [
                "publish_local_catalog.py",
                "--catalog-file",
                str(catalog_path),
                "--central-url",
                "http://catalog.example/catalog",
                "--webid",
                webid,
            ]

            with patch.object(sys, "argv", argv), patch.object(
                publish_local_catalog, "urlopen", fake_urlopen
            ):
                self.assertEqual(publish_local_catalog.main(), 0)

        headers = dict(captured["request"].header_items())
        self.assertEqual(headers["X-participant-webid"], webid)
        self.assertEqual(headers["X-participant-id"], webid)
        self.assertEqual(captured["timeout"], 20)


if __name__ == "__main__":
    main()
