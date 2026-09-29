"""Administrator-maintained registry. Identifiers are bindings, not authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import PublicationError


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Participant(Record):
    id: str = Field(min_length=1)
    active: bool


class Identity(Record):
    type: str = Field(min_length=1)
    value: str = Field(min_length=1)


class Principal(Record):
    id: str = Field(min_length=1)
    participantId: str = Field(min_length=1)
    active: bool
    tokenSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    identities: list[Identity] = Field(default_factory=list)


class Source(Record):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    participantId: str = Field(min_length=1)
    kind: Literal["edc", "solid"]
    catalogIri: str = Field(min_length=1)
    active: bool


class Grant(Record):
    principalId: str = Field(min_length=1)
    sourceId: str = Field(min_length=1)
    operations: list[Literal["publish", "withdraw"]]
    active: bool


class RegistryDocument(Record):
    participants: list[Participant]
    principals: list[Principal]
    sources: list[Source]
    grants: list[Grant]


def _unique(records, attribute: str) -> dict:
    result = {}
    for record in records:
        key = getattr(record, attribute)
        if key in result:
            raise ValueError(f"Duplicate {attribute}")
        result[key] = record
    return result


class Registry:
    def __init__(self, document: RegistryDocument):
        self.participants = _unique(document.participants, "id")
        self.principals = _unique(document.principals, "id")
        self.sources = _unique(document.sources, "id")
        _unique(document.sources, "catalogIri")
        _unique(document.principals, "tokenSha256")
        self.grants = document.grants
        for principal in document.principals:
            if principal.participantId not in self.participants:
                raise ValueError("Principal references an unknown participant")
        for source in document.sources:
            if source.participantId not in self.participants:
                raise ValueError("Source references an unknown participant")
            if not urlsplit(source.catalogIri).scheme or re.search(
                r'[<>"{}|^`\\\s]', source.catalogIri
            ):
                raise ValueError("Catalog identifiers must be absolute IRIs")
        for grant in document.grants:
            if grant.principalId not in self.principals or grant.sourceId not in self.sources:
                raise ValueError("Grant references an unknown principal or source")

    def authenticate(self, authorization: str | None) -> Principal:
        if not authorization:
            raise PublicationError(
                401, "authentication_required", "A publisher bearer token is required"
            )
        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise PublicationError(
                401, "authentication_required", "A publisher bearer token is required"
            )
        digest = hashlib.sha256(parts[1].strip().encode()).hexdigest()
        principal = next(
            (
                item
                for item in self.principals.values()
                if hmac.compare_digest(item.tokenSha256, digest)
            ),
            None,
        )
        if principal is None:
            raise PublicationError(401, "authentication_required", "Invalid publisher credential")
        if not self.principal_active(principal.id):
            raise PublicationError(
                403, "membership_required", "Publishing principal or participant is inactive"
            )
        return principal

    def principal_active(self, principal_id: str) -> bool:
        principal = self.principals.get(principal_id)
        return bool(
            principal and principal.active and self.participants[principal.participantId].active
        )

    def source_active(self, source_id: str) -> bool:
        source = self.sources.get(source_id)
        return bool(source and source.active and self.participants[source.participantId].active)

    def permitted(self, principal_id: str, source_id: str, operation: str) -> bool:
        return (
            self.principal_active(principal_id)
            and self.source_active(source_id)
            and any(
                grant.active
                and grant.principalId == principal_id
                and grant.sourceId == source_id
                and operation in grant.operations
                for grant in self.grants
            )
        )

    def authorize(self, principal: Principal, source_id: str, operation: str | None) -> Source:
        source = self.sources.get(source_id)
        if source is None:
            raise PublicationError(404, "source_not_found", "Source is not registered")
        permitted = (
            self.permitted(principal.id, source_id, operation)
            if operation
            else any(self.permitted(principal.id, source_id, op) for op in ("publish", "withdraw"))
        )
        if not permitted:
            raise PublicationError(
                403, "source_forbidden", "No active grant for this source and operation"
            )
        return source

    def visible(self, state: dict) -> bool:
        source = self.sources.get(state["sourceId"])
        return bool(
            source
            and source.catalogIri == state["catalogIri"]
            and source.participantId == state["participantId"]
            and not state["withdrawn"]
            and self.permitted(state["principalId"], source.id, "publish")
        )


class FileRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.load()  # Reject unusable configuration at startup.

    def load(self) -> Registry:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return Registry(RegistryDocument.model_validate(raw))
        except (OSError, ValueError, ValidationError, RecursionError) as exc:
            # Do not return registry contents, credential hashes or parser diagnostics.
            raise PublicationError(
                503, "registry_unavailable", "Publication registry is unavailable or invalid"
            ) from exc
