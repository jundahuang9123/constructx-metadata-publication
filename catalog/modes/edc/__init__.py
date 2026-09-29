from dataclasses import dataclass

from core.interfaces.discovery import DiscoveryService
from core.interfaces.ingest import IngestSource
from core.interfaces.registry import RegistryCheck
from core.interfaces.store import CatalogStore
from core.interfaces.validation import ValidationGate
from core.shared.shacl_validate import ShaclValidationGate
from modes.edc.discovery import EdcDiscovery
from modes.edc.ingest import EdcIngest
from modes.edc.registry import EdcRegistryCheck
from modes.edc.store import EdcStore


@dataclass(frozen=True)
class EdcMode:
    registry: RegistryCheck
    validation: ValidationGate
    store: CatalogStore
    ingest: IngestSource
    discovery: DiscoveryService
    name: str = "edc"


def register() -> EdcMode:
    registry = EdcRegistryCheck()
    validation = ShaclValidationGate()
    store = EdcStore()
    ingest = EdcIngest()
    discovery = EdcDiscovery()
    return EdcMode(
        registry=registry,
        validation=validation,
        store=store,
        ingest=ingest,
        discovery=discovery,
    )
