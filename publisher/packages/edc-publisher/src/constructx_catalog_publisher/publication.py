"""Client for the source publication API; retries reuse the saved request verbatim."""

from __future__ import annotations

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .converter import PROFILE_IRI
from .validation import profile_hash

MAX_BYTES = 2 * 1024 * 1024


class PublicationError(RuntimeError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicationError("Catalog redirects are refused; configure the final endpoint.")


def base_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "?" in url
        or "#" in url
        or any(c.isspace() or ord(c) < 32 for c in url)
    ):
        raise PublicationError(
            "Catalog URL must be HTTP(S), without credentials, query or fragment."
        )
    return url.rstrip("/")


class PublicationClient:
    def __init__(self, url: str, token: str, timeout: int = 30):
        self.url = base_url(url)
        if not token or any(ord(c) < 32 or ord(c) == 127 for c in token):
            raise PublicationError("A catalog publishing token is required.")
        self._token = token
        self.timeout = timeout
        self._opener = build_opener(NoRedirects())

    def request(
        self, method: str, path: str, body: bytes | None = None, headers: dict | None = None
    ) -> tuple[int, dict]:
        if body is not None and len(body) > MAX_BYTES:
            raise PublicationError("Publication envelope exceeds the 2 MiB limit.")
        request = Request(
            self.url + path,
            data=body,
            method=method,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status, raw = response.status, response.read(MAX_BYTES + 1)
        except HTTPError as exc:
            status, raw = exc.code, exc.read(MAX_BYTES + 1)
        except PublicationError:
            raise
        except (URLError, OSError, HTTPException):
            raise PublicationError(
                "Catalog request failed. A mutation may have committed; retry the saved bundle unchanged."
            ) from None
        if len(raw) > MAX_BYTES:
            raise PublicationError("Catalog response exceeds the supported size.")
        try:
            decoded = json.loads(raw)
        except (ValueError, UnicodeError):
            raise PublicationError(
                f"Catalog returned a non-JSON response (HTTP {status})."
            ) from None
        if not isinstance(decoded, dict):
            raise PublicationError("Catalog returned an unexpected response shape.")
        return status, decoded

    def baseline(self, source_id: str, catalog_iri: str) -> str:
        status, profiles = self.request("GET", "/v1/profiles")
        if status != 200 or not any(
            p.get("profileIri") == PROFILE_IRI and p.get("profileShapeHash") == profile_hash()
            for p in profiles.get("profiles", [])
        ):
            raise PublicationError(
                "Catalog does not support this exact provisional profile and shape hash."
            )
        status, state = self.request("GET", "/v1/sources/" + quote(source_id, safe="") + "/state")
        if status == 404 and state.get("error") == "source_unpublished":
            return "none"
        if status != 200:
            raise PublicationError(
                f"Cannot read publication baseline (HTTP {status}). Check registration and source grant."
            )
        if state.get("catalogIri") != catalog_iri:
            raise PublicationError("Configured catalogIri does not match the registered source.")
        revision = state.get("revision")
        if (
            not isinstance(revision, str)
            or not revision.startswith("r")
            or not revision[1:].isdigit()
        ):
            raise PublicationError("Catalog returned an invalid publication revision.")
        return '"' + revision + '"'

    def submit(
        self, source_id: str, body: bytes | None, revision: str, key: str, method: str = "PUT"
    ) -> dict:
        status, result = self.request(
            method,
            "/v1/sources/" + quote(source_id, safe="") + "/catalog",
            body,
            {"Publication-If-Revision": revision, "Idempotency-Key": key},
        )
        if status not in {200, 201} or result.get("accepted") is not True:
            code = result.get("error", "request_rejected")
            if not isinstance(code, str) or not code.replace("_", "").isalnum():
                code = "request_rejected"
            raise PublicationError(
                f"Publication rejected (HTTP {status}, {code}); accepted metadata was not confirmed changed. For revision conflicts, prepare a new harvest."
            )
        return result
