from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatasetResult:
    dataset_id: str
    title: str | None = None
    type: str | None = None
    provider: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RdfTriple:
    subject: str
    predicate: str
    object: str


@dataclass(frozen=True)
class DatasetDetail(DatasetResult):
    types: list[str] = field(default_factory=list)
    triples: list[RdfTriple] = field(default_factory=list)


@dataclass(frozen=True)
class CatalogStatus:
    mode: str
    operational: bool
    dataset_count: int = 0
    graph_count: int = 0
    registry_reachable: bool | None = None
    detail: str | None = None
    dependencies: dict[str, object] | None = None


class DiscoveryService(ABC):
    @abstractmethod
    def list_datasets(self) -> list[DatasetResult]:
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> CatalogStatus:
        raise NotImplementedError

    @abstractmethod
    def get_dataset(self, dataset_id: str) -> DatasetDetail | None:
        raise NotImplementedError
