from abc import ABC, abstractmethod


class RegistryCheck(ABC):
    """Verify participant membership in the active substrate's registry.

    Implementations may raise when a substrate is not wired yet or when the
    registry cannot be reached. Callers should fail closed when membership
    cannot be verified.
    """

    @abstractmethod
    def is_member(self, participant_id: str) -> bool:
        raise NotImplementedError

