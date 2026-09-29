"""Read a complete, stable-looking inventory from an EDC Management API.

Two matching scans are evidence of stability, not an atomic database snapshot.
An empty page terminates each scan: a short page may reflect a server-side cap.
All failures abort harvesting rather than returning a partial inventory.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

EDC_NAMESPACE = "https://w3id.org/edc/v0.0.1/ns/"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class InventoryError(RuntimeError):
    """An inventory could not be safely and completely obtained."""


@dataclass(frozen=True)
class InventorySnapshot:
    assets: list[dict]
    started_at: str
    finished_at: str
    digest: str
    pages: int
    verification: str


def _id_value(value: object) -> str | None:
    if isinstance(value, list) and len(value) == 1:
        return _id_value(value[0])
    if isinstance(value, dict) and "@value" in value:
        return _id_value(value["@value"])
    if isinstance(value, str) and value.strip():
        return value
    return None


def asset_id(asset: dict) -> str:
    """Read an asset identifier in the supported compact or expanded forms.

    Conflicting identifiers are rejected rather than selecting an ambiguous ID.
    Values in exceptions deliberately exclude supplied metadata.
    """
    if not isinstance(asset, dict):
        raise InventoryError("Inventory contains a non-object asset.")
    ids = []
    for key in ("@id", "id", "edc:id", EDC_NAMESPACE + "id"):
        if key in asset:
            candidate = _id_value(asset[key])
            if candidate is None:
                raise InventoryError("Inventory contains a missing or invalid asset identifier.")
            ids.append(candidate)
    if not ids:
        raise InventoryError("Inventory contains an asset without an identifier.")
    if len(set(ids)) != 1:
        raise InventoryError("Inventory contains conflicting asset identifiers.")
    return ids[0]


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise InventoryError("Inventory contains invalid JSON values.") from None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InventoryError("Management API redirects are not allowed.")


def _validate_url(base_url: str, query_path: str) -> str:
    if not isinstance(base_url, str) or any(char.isspace() for char in base_url):
        raise ValueError("Management API base URL must be an absolute HTTP(S) URL.")
    try:
        parsed = urlsplit(base_url)
        _ = parsed.port
        valid = (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and "@" not in parsed.netloc
            and not parsed.query
            and not parsed.fragment
            and "?" not in base_url
            and "#" not in base_url
            and not any(ord(char) < 32 or ord(char) == 127 for char in base_url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "Management API base URL must be HTTP(S), without credentials, query or fragment."
        )
    if (
        not isinstance(query_path, str)
        or not query_path.startswith("/")
        or query_path.startswith("//")
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in query_path)
        or "?" in query_path
        or "#" in query_path
        or "\\" in query_path
        or any(segment in (".", "..") for segment in query_path.split("/"))
    ):
        raise ValueError("Asset query path must be an absolute URL path without query or fragment.")
    return base_url.rstrip("/") + query_path


class InventoryClient:
    """Management API asset reader using the connector's ``x-api-key`` header.

    ``base_url`` includes the Management API prefix (for example
    ``http://127.0.0.1:29110/management``). HTTP is supported for deployments
    with a trusted local transport; configure HTTPS for credentials over a
    network. ``pages`` counts responses across both scans, including empty
    terminal pages. ``max_pages`` bounds each scan independently.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        query_path: str = "/v3/assets/request",
        page_size: int = 100,
        max_pages: int = 1000,
        timeout: float = 30,
        sort_field: str = "id",
    ) -> None:
        self._url = _validate_url(base_url, query_path)
        if (
            not isinstance(api_key, str)
            or not api_key
            or any(ord(c) < 32 or ord(c) == 127 for c in api_key)
        ):
            raise ValueError(
                "A non-empty Management API key without control characters is required."
            )
        for value, label in ((page_size, "page_size"), (max_pages, "max_pages")):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive integer.")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a positive finite number.")
        if not isinstance(sort_field, str) or not sort_field.strip():
            raise ValueError("sort_field must be a non-empty string.")
        self._api_key = api_key
        self.page_size = page_size
        self.max_pages = max_pages
        self.timeout = timeout
        self.sort_field = sort_field
        self._opener = build_opener(_RejectRedirects())

    def _page(self, offset: int) -> list[dict]:
        payload = {
            "@context": {"@vocab": EDC_NAMESPACE},
            "@type": "QuerySpec",
            "offset": offset,
            "limit": self.page_size,
            "sortField": self.sort_field,
            "sortOrder": "ASC",
            "filterExpression": [],
        }
        request = Request(
            self._url,
            data=_canonical(payload),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise InventoryError(f"Management API returned HTTP {response.status}.")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except InventoryError:
            raise
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise InventoryError("Management API redirects are not allowed.") from None
            raise InventoryError(f"Management API returned HTTP {exc.code}.") from None
        except (URLError, OSError, HTTPException, ValueError, UnicodeError):
            raise InventoryError(
                "Management API request failed; check endpoint, transport and credentials."
            ) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise InventoryError("Management API response exceeds the permitted size.")
        try:

            def reject_constant(value: str) -> None:
                raise ValueError("Invalid JSON constant")

            page = json.loads(raw, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise InventoryError("Management API returned malformed JSON.") from None
        if not isinstance(page, list):
            raise InventoryError("Management API asset query must return a JSON array.")
        if any(not isinstance(asset, dict) for asset in page):
            raise InventoryError("Inventory contains a non-object asset.")
        return page

    def _scan(self) -> tuple[dict[str, dict], int]:
        assets: dict[str, dict] = {}
        offset = 0
        page_digests: set[str] = set()
        for page_number in range(1, self.max_pages + 1):
            page = self._page(offset)
            if not page:
                return assets, page_number
            page_digest = hashlib.sha256(_canonical(page)).hexdigest()
            if page_digest in page_digests:
                raise InventoryError(
                    "Management API repeated a non-empty page; inventory is incomplete."
                )
            page_digests.add(page_digest)
            for asset in page:
                identifier = asset_id(asset)
                if identifier in assets:
                    raise InventoryError(
                        "Management API returned a duplicate asset identifier; inventory is incomplete."
                    )
                assets[identifier] = asset
            offset += len(page)
        raise InventoryError(
            "Management API inventory exceeded max_pages before an empty terminal page."
        )

    def harvest(self) -> InventorySnapshot:
        """Return inventory only when two complete scans match by ID and content."""
        started_at = _now()
        first, first_pages = self._scan()
        second, second_pages = self._scan()
        first_bytes = _canonical(first)
        second_bytes = _canonical(second)
        if first_bytes != second_bytes:
            raise InventoryError(
                "Management API inventory changed between scans; publication was aborted."
            )
        return InventorySnapshot(
            assets=[second[identifier] for identifier in sorted(second)],
            started_at=started_at,
            finished_at=_now(),
            digest=hashlib.sha256(second_bytes).hexdigest(),
            pages=first_pages + second_pages,
            verification="two-matching-scans",
        )
