# Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
"""Fuseki graph-store and SPARQL helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class FusekiSettings:
    dataset_url: str
    username: str = "admin"
    password: str = "admin"
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "FusekiSettings":
        return cls(
            dataset_url=os.getenv("FUSEKI_URL", "http://localhost:3030/solid"),
            username=os.getenv("FUSEKI_USER", "admin"),
            password=os.getenv("FUSEKI_PASSWORD", "admin"),
            timeout_seconds=float(os.getenv("FUSEKI_TIMEOUT_SECONDS", "10")),
        )


class FusekiClient:
    def __init__(
        self,
        settings: FusekiSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or FusekiSettings.from_env()
        self.dataset_url = self.settings.dataset_url.rstrip("/")
        self._client = http_client or httpx.Client(timeout=self.settings.timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _endpoint(self, name: str) -> str:
        if self.dataset_url.endswith(f"/{name}"):
            return self.dataset_url
        return f"{self.dataset_url}/{name}"

    @property
    def _auth(self) -> tuple[str, str]:
        return (self.settings.username, self.settings.password)

    def replace_named_graph(
        self,
        graph_uri: str,
        rdf_payload: str | bytes,
        *,
        content_type: str = "text/turtle",
    ) -> None:
        data_endpoint = self._endpoint("data")
        delete_response = self._client.delete(
            data_endpoint,
            params={"graph": graph_uri},
            auth=self._auth,
        )
        if delete_response.status_code not in {200, 202, 204, 404}:
            raise RuntimeError(
                f"Failed to delete named graph {graph_uri}: "
                f"{delete_response.status_code} {delete_response.text}"
            )

        insert_response = self._client.post(
            data_endpoint,
            params={"graph": graph_uri},
            headers={"Content-Type": content_type},
            content=rdf_payload,
            auth=self._auth,
        )
        if insert_response.status_code not in {200, 201, 202, 204}:
            raise RuntimeError(
                f"Failed to insert named graph {graph_uri}: "
                f"{insert_response.status_code} {insert_response.text}"
            )

    def query(self, sparql: str) -> list[dict[str, object]]:
        response = self._client.post(
            self._endpoint("query"),
            data={"query": sparql},
            headers={"Accept": "application/sparql-results+json"},
            auth=self._auth,
        )
        if response.status_code not in {200, 201, 202, 204}:
            raise RuntimeError(f"SPARQL query failed: {response.status_code} {response.text}")
        if not response.content:
            return []

        payload = response.json()
        rows: list[dict[str, object]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            row: dict[str, object] = {}
            for key, value in binding.items():
                row[key] = value.get("value")
            rows.append(row)
        return rows

