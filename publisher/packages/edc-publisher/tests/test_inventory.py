"""Offline tests for full and stable Management API inventory retrieval."""

from __future__ import annotations

import io
import json
import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from constructx_catalog_publisher.inventory import (
    EDC_NAMESPACE,
    InventoryClient,
    InventoryError,
    _RejectRedirects,
    asset_id,
)


class Response:
    def __init__(self, value=None, *, raw=None, status=200):
        self.status = status
        self.raw = json.dumps(value).encode() if raw is None else raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.raw[:limit]


class Opener:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def open(self, request, timeout):
        query = json.loads(request.data)
        self.requests.append((request, query, timeout))
        return self.handler(query, len(self.requests))


def client_for(handler, **kwargs):
    client = InventoryClient("http://127.0.0.1:29110/management", "test-key", **kwargs)
    client._opener = Opener(handler)
    return client


class InventoryTests(unittest.TestCase):
    def test_server_caps_short_pages_and_offset_uses_actual_rows(self):
        assets = [{"@id": str(i), "properties": {"name": f"Asset {i}"}} for i in range(5)]
        client = client_for(
            lambda query, _: Response(assets[query["offset"] : query["offset"] + 2]), page_size=100
        )
        result = client.harvest()
        self.assertEqual(result.assets, assets)
        self.assertEqual(result.pages, 8)
        self.assertEqual(result.verification, "two-matching-scans")
        self.assertRegex(result.digest, r"^[0-9a-f]{64}$")
        self.assertTrue(result.started_at.endswith("Z"))
        self.assertGreaterEqual(result.finished_at, result.started_at)
        requests = client._opener.requests
        self.assertEqual([query["offset"] for _, query, _ in requests], [0, 2, 4, 5] * 2)
        request, query, timeout = requests[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:29110/management/v3/assets/request")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-api-key"), "test-key")
        self.assertEqual(timeout, 30)
        self.assertEqual(
            query,
            {
                "@context": {"@vocab": EDC_NAMESPACE},
                "@type": "QuerySpec",
                "offset": 0,
                "limit": 100,
                "sortField": "id",
                "sortOrder": "ASC",
                "filterExpression": [],
            },
        )

    def test_empty_inventory_requires_two_empty_responses(self):
        client = client_for(lambda *_: Response([]))
        result = client.harvest()
        self.assertEqual(result.assets, [])
        self.assertEqual(result.pages, 2)

    def test_row_and_object_key_order_do_not_change_verification_or_digest(self):
        first = [{"@id": "a", "properties": {"x": 1, "y": 2}}, {"@id": "b"}]
        second = [{"@id": "b"}, {"properties": {"y": 2, "x": 1}, "@id": "a"}]
        responses = [first, [], second, []]
        result = client_for(
            lambda _, count, responses=responses: Response(responses[count - 1])
        ).harvest()
        stable = client_for(
            lambda query, _: Response(first if query["offset"] == 0 else [])
        ).harvest()
        self.assertEqual(result.digest, stable.digest)
        self.assertEqual([asset_id(asset) for asset in result.assets], ["a", "b"])

    def test_mismatch_in_contents_or_identifiers_aborts(self):
        for later in ([{"@id": "a", "properties": {"name": "changed"}}], [{"@id": "b"}], []):
            with self.subTest(later=later):
                responses = [[{"@id": "a"}], [], later, []]
                client = client_for(
                    lambda _, count, responses=responses: Response(responses[count - 1])
                )
                with self.assertRaisesRegex(InventoryError, "changed between scans"):
                    client.harvest()

    def test_missing_invalid_and_conflicting_identifiers_abort(self):
        for asset in ({}, {"@id": ""}, {"@id": 12}, {"@id": "a", "id": "b"}, {"id": ["a", "b"]}):
            with self.subTest(asset=asset):
                client = client_for(lambda *_, asset=asset: Response([asset]))
                with self.assertRaises(InventoryError):
                    client.harvest()

    def test_supported_identifier_forms(self):
        for key in ("@id", "id", "edc:id", EDC_NAMESPACE + "id"):
            for value in ("asset-a", [{"@value": "asset-a"}], {"@value": "asset-a"}):
                with self.subTest(key=key, value=value):
                    self.assertEqual(asset_id({key: value}), "asset-a")
        self.assertEqual(asset_id({"@id": "a", "id": "a"}), "a")

    def test_duplicate_identifiers_within_page_abort(self):
        client = client_for(
            lambda *_: Response([{"@id": "a"}, {"@id": "a", "properties": {"name": "other"}}])
        )
        with self.assertRaisesRegex(InventoryError, "duplicate asset identifier"):
            client.harvest()

    def test_duplicate_identifiers_across_different_pages_abort(self):
        pages = [[{"@id": "a"}], [{"@id": "a", "properties": {"name": "other"}}]]
        client = client_for(lambda _, count: Response(pages[count - 1]))
        with self.assertRaisesRegex(InventoryError, "duplicate asset identifier"):
            client.harvest()

    def test_repeated_page_aborts(self):
        client = client_for(lambda *_: Response([{"@id": "a"}]))
        with self.assertRaisesRegex(InventoryError, "repeated a non-empty page"):
            client.harvest()

    def test_bound_requires_observed_empty_page(self):
        client = client_for(lambda query, _: Response([{"@id": str(query["offset"])}]), max_pages=2)
        with self.assertRaisesRegex(InventoryError, "exceeded max_pages"):
            client.harvest()
        self.assertEqual(len(client._opener.requests), 2)

    def test_malformed_and_non_array_responses_abort(self):
        for raw in (
            b"not-json",
            b'{"assets": []}',
            b"null",
            b"[42]",
            b'[{"@id":"a","x":NaN}]',
            b"\xff",
        ):
            with self.subTest(raw=raw):
                client = client_for(lambda *_, raw=raw: Response(raw=raw))
                with self.assertRaises(InventoryError):
                    client.harvest()

    def test_oversized_response_aborts(self):
        client = client_for(lambda *_: Response(raw=b" " * 11))
        with patch("constructx_catalog_publisher.inventory.MAX_RESPONSE_BYTES", 10):
            with self.assertRaisesRegex(InventoryError, "exceeds the permitted size"):
                client.harvest()

    def test_http_and_transport_errors_exclude_response_secrets(self):
        failures = [
            HTTPError(
                "https://private.invalid/", 401, "sensitive body", {}, io.BytesIO(b"super-secret")
            ),
            HTTPError(
                "https://private.invalid/", 500, "sensitive body", {}, io.BytesIO(b"super-secret")
            ),
            URLError("super-secret"),
            TimeoutError("super-secret"),
            IncompleteRead(b"super-secret"),
        ]
        for failure in failures:

            def fail(*_, failure=failure):
                raise failure

            with self.subTest(failure=type(failure).__name__):
                client = client_for(fail)
                with self.assertRaises(InventoryError) as caught:
                    client.harvest()
                self.assertNotIn("super-secret", str(caught.exception))
                self.assertNotIn("sensitive", str(caught.exception))
                self.assertNotIn("private.invalid", str(caught.exception))

    def test_failure_after_first_page_does_not_return_partial_inventory(self):
        def handler(query, _):
            if query["offset"]:
                raise URLError("failure")
            return Response([{"@id": "a"}])

        with self.assertRaises(InventoryError):
            client_for(handler).harvest()

    def test_redirect_handler_refuses_before_following(self):
        request = Request(
            "https://provider.invalid/management/v3/assets/request",
            data=b"{}",
            headers={"x-api-key": "super-secret"},
        )
        for status in (301, 302, 303, 307, 308):
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(InventoryError, "redirects are not allowed"),
            ):
                _RejectRedirects().redirect_request(
                    request, None, status, "redirect", {}, "https://other.invalid/stolen"
                )
        client = InventoryClient("https://provider.invalid/management", "super-secret")
        self.assertTrue(
            any(isinstance(handler, _RejectRedirects) for handler in client._opener.handlers)
        )

    def test_http_redirect_error_is_sanitized(self):
        def fail(*_):
            raise HTTPError("https://secret.invalid/", 307, "secret redirect", {}, None)

        with self.assertRaisesRegex(InventoryError, "redirects are not allowed"):
            client_for(fail).harvest()

    def test_url_and_configuration_validation(self):
        invalid_urls = (
            "ftp://provider.invalid/",
            "https:///management",
            "https://user:secret@provider.invalid/",
            "https://provider.invalid/management?token=secret",
            "https://provider.invalid/management#fragment",
            "https://provider.invalid:bad/management",
            "https://provider.invalid/management?",
            "https://provider.invalid/management#",
            "https://provider.invalid/\nmanagement",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                InventoryClient(url, "key")
        for path in (
            "https://other.invalid/",
            "//other.invalid/",
            "/v3/assets?x=y",
            "/v3/assets#x",
            "/../assets",
            "/v3/\\assets",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                InventoryClient("https://provider.invalid/management", "key", query_path=path)
        for kwargs in (
            {"page_size": 0},
            {"max_pages": -1},
            {"page_size": True},
            {"timeout": float("inf")},
            {"timeout": 0},
            {"sort_field": ""},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                InventoryClient("https://provider.invalid/management", "key", **kwargs)
        for key in ("", "key\r\ninjection"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                InventoryClient("https://provider.invalid/management", key)

    def test_configurable_path_and_sort_field(self):
        client = client_for(
            lambda *_: Response([]), query_path="/v4/assets/request", sort_field="custom:id"
        )
        client.harvest()
        request, query, _ = client._opener.requests[0]
        self.assertTrue(request.full_url.endswith("/v4/assets/request"))
        self.assertEqual(query["sortField"], "custom:id")


if __name__ == "__main__":
    unittest.main()
