from abc import ABC, abstractmethod

from fastapi import APIRouter


class IngestSource(ABC):
    """Mode-specific push entrypoint.

    Expected push contract:
    POST /catalog with an RDF request body, a content type that identifies the
    RDF serialization, and a declared participant id. The participant id may be
    supplied as the X-Participant-Id header or participant_id query/form field.

    Successful pushes return 200. Registry rejection or SHACL rejection returns
    a readable 4xx response with errors.
    """

    @abstractmethod
    def routes(self) -> APIRouter:
        raise NotImplementedError
