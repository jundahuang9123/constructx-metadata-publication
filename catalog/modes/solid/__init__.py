from dataclasses import dataclass

from core.interfaces.discovery import DiscoveryService
from core.interfaces.ingest import IngestSource
from core.interfaces.registry import RegistryCheck
from core.interfaces.store import CatalogStore
from core.interfaces.validation import ValidationGate
from core.shared.shacl_validate import ShaclValidationGate
from modes.solid.auth import SolidAuth, build_solid_auth_from_env
from modes.solid.discovery import SolidDiscovery
from modes.solid.ingest import SolidIngest
from modes.solid.registry import SolidRegistryCheck
from modes.solid.store import SolidStore


@dataclass(frozen=True)
class SolidMode:
    registry: RegistryCheck
    validation: ValidationGate
    store: CatalogStore
    ingest: IngestSource
    discovery: DiscoveryService
    auth: SolidAuth
    name: str = "solid"


def register() -> SolidMode:
    registry = SolidRegistryCheck()
    validation = ShaclValidationGate()
    store = SolidStore()
    auth = build_solid_auth_from_env()
    ingest = SolidIngest(registry=registry, validation=validation, store=store, auth=auth)
    discovery = SolidDiscovery(store=store, registry=registry)
    return SolidMode(
        registry=registry,
        validation=validation,
        store=store,
        ingest=ingest,
        discovery=discovery,
        auth=auth,
    )
