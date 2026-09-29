"""Solid-mode store implementation."""

from __future__ import annotations

from urllib.parse import quote, unquote

from core.interfaces.store import CatalogStore
from core.shared.fuseki import FusekiClient


GRAPH_PREFIX = "urn:catalog:"


def graph_uri_for_participant(participant_id: str) -> str:
    return f"{GRAPH_PREFIX}{quote(participant_id, safe='')}"


def participant_from_graph_uri(graph_uri: str | None) -> str | None:
    if not graph_uri or not graph_uri.startswith(GRAPH_PREFIX):
        return None
    return unquote(graph_uri[len(GRAPH_PREFIX) :])


class SolidStore(CatalogStore):
    def __init__(self, fuseki: FusekiClient | None = None) -> None:
        self.fuseki = fuseki or FusekiClient()

    def replace_graph(self, graph_id: str, rdf_payload: str) -> None:
        self.fuseki.replace_named_graph(graph_id, rdf_payload, content_type="text/turtle")

    def query(self, sparql: str) -> list[dict[str, object]]:
        return self.fuseki.query(sparql)

