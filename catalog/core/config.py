import os
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol

from core.interfaces.discovery import DiscoveryService
from core.interfaces.ingest import IngestSource
from core.interfaces.registry import RegistryCheck
from core.interfaces.store import CatalogStore
from core.interfaces.validation import ValidationGate


class ModeRegistration(Protocol):
    name: str
    registry: RegistryCheck
    validation: ValidationGate
    store: CatalogStore
    ingest: IngestSource
    discovery: DiscoveryService


@dataclass(frozen=True)
class CatalogSettings:
    mode: str


def get_settings() -> CatalogSettings:
    return CatalogSettings(mode=os.getenv("CATALOG_MODE", "").strip().lower())


def load_active_mode() -> ModeRegistration:
    settings = get_settings()
    if settings.mode not in {"solid", "edc"}:
        raise RuntimeError("CATALOG_MODE must be set to either 'solid' or 'edc'")

    module = import_module(f"modes.{settings.mode}")
    return module.register()
