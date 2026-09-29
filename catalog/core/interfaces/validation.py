from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class ValidationGate(ABC):
    @abstractmethod
    def validate(self, rdf_payload: str, *, format: str | None = None) -> ValidationResult:
        raise NotImplementedError

