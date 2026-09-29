# Mirrors modes/solid/discovery.py; wire when EDC substrate is ready.
"""EDC-mode discovery implementation."""

from core.interfaces.discovery import CatalogStatus, DatasetDetail, DatasetResult, DiscoveryService


class EdcDiscovery(DiscoveryService):
    def list_datasets(self) -> list[DatasetResult]:
        return []

    def get_status(self) -> CatalogStatus:
        return CatalogStatus(
            mode="edc",
            operational=False,
            detail="EDC mode not wired for testing yet",
            dependencies={"fuseki": None, "registry": None},
        )

    def get_dataset(self, dataset_id: str) -> DatasetDetail | None:
        return None
