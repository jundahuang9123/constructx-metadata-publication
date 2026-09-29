# Mirrors modes/solid/store.py; wire when EDC substrate is ready.
"""EDC-mode store implementation."""

from core.interfaces.store import CatalogStore


class EdcStore(CatalogStore):
    def replace_graph(self, graph_id: str, rdf_payload: str) -> None:
        raise NotImplementedError("EDC mode not wired for testing yet")

    def query(self, sparql: str) -> list[dict[str, object]]:
        raise NotImplementedError("EDC mode not wired for testing yet")

