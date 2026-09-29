# Mirrors modes/solid/registry.py; wire when EDC substrate is ready.

from core.interfaces.registry import RegistryCheck


class EdcRegistryCheck(RegistryCheck):
    def is_member(self, participant_id: str) -> bool:
        raise NotImplementedError("EDC registry not wired yet")

