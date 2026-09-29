"""Solid-mode push ingestion."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from core.interfaces.ingest import IngestSource
from core.interfaces.registry import RegistryCheck
from core.interfaces.store import CatalogStore
from core.interfaces.validation import ValidationGate
from core.shared.rdf import guess_rdflib_format, serialize_rdf_to_turtle
from modes.solid.auth import SolidAuth, SolidAuthError
from modes.solid.registry import SolidRegistryError
from modes.solid.store import graph_uri_for_participant

logger = logging.getLogger(__name__)


def _error_response(
    *,
    status_code: int,
    error: str,
    detail: str,
    stage: str,
    request_id: str,
    errors: list[str] | None = None,
) -> JSONResponse:
    payload: dict[str, object] = {
        "error": error,
        "detail": detail,
        "stage": stage,
        "request_id": request_id,
    }
    if errors is not None:
        payload["errors"] = errors
    return JSONResponse(status_code=status_code, content=payload)


class SolidIngest(IngestSource):
    def __init__(
        self,
        registry: RegistryCheck,
        validation: ValidationGate,
        store: CatalogStore,
        auth: SolidAuth,
    ) -> None:
        self.registry = registry
        self.validation = validation
        self.store = store
        self.auth = auth

    def routes(self) -> APIRouter:
        router = APIRouter()

        @router.post("/catalog", response_model=None)
        async def push_catalog(
            request: Request,
            participant_header: str | None = Header(default=None, alias="X-Participant-Id"),
            participant_query: str | None = Query(default=None, alias="participant_id"),
            request_id_header: str | None = Header(default=None, alias="X-Request-Id"),
        ):
            request_id = request_id_header or str(uuid4())

            try:
                user = self.auth.authenticate(
                    request,
                    declared_participant_id=participant_header or participant_query,
                )
            except SolidAuthError as exc:
                logger.info(
                    "Solid push rejected at auth stage",
                    extra={"request_id": request_id, "stage": "auth", "error": exc.error},
                )
                return _error_response(
                    status_code=exc.status_code,
                    error=exc.error,
                    detail=exc.detail,
                    stage="auth",
                    request_id=request_id,
                )

            participant_id = user.webid
            logger.info(
                "Solid push authenticated",
                extra={
                    "request_id": request_id,
                    "stage": "auth",
                    "webid": participant_id,
                    "auth_mode": user.auth_mode,
                },
            )

            try:
                registered = self.registry.is_member(participant_id)
            except SolidRegistryError as exc:
                logger.warning(
                    "Solid push rejected because registry lookup failed",
                    extra={"request_id": request_id, "stage": "registry", "webid": participant_id},
                )
                return _error_response(
                    status_code=422,
                    error="registry_unavailable",
                    detail=str(exc),
                    stage="registry",
                    request_id=request_id,
                )
            except Exception as exc:
                logger.warning(
                    "Solid push rejected because registry lookup failed",
                    extra={"request_id": request_id, "stage": "registry", "webid": participant_id},
                    exc_info=True,
                )
                return _error_response(
                    status_code=422,
                    error="registry_lookup_failed",
                    detail=f"Solid registry lookup failed: {exc}",
                    stage="registry",
                    request_id=request_id,
                )

            if not registered:
                logger.info(
                    "Solid push rejected because participant is not registered",
                    extra={"request_id": request_id, "stage": "registry", "webid": participant_id},
                )
                return _error_response(
                    status_code=403,
                    error="participant_not_registered",
                    detail=f"participant not registered in Solid registry: {participant_id}",
                    stage="registry",
                    request_id=request_id,
                )

            raw_body = (await request.body()).decode("utf-8")
            content_type = request.headers.get("content-type")
            rdf_format = guess_rdflib_format(content_type)
            validation = self.validation.validate(raw_body, format=rdf_format)
            if not validation.ok:
                logger.info(
                    "Solid push rejected by SHACL validation",
                    extra={"request_id": request_id, "stage": "validation", "webid": participant_id},
                )
                return _error_response(
                    status_code=422,
                    error="validation_failed",
                    detail="RDF payload failed parsing or SHACL validation",
                    stage="validation",
                    request_id=request_id,
                    errors=validation.errors,
                )

            try:
                normalized_turtle = serialize_rdf_to_turtle(raw_body, format=rdf_format)
                graph_id = graph_uri_for_participant(participant_id)
                self.store.replace_graph(graph_id, normalized_turtle)
            except Exception as exc:
                logger.exception(
                    "Solid push failed at store stage",
                    extra={"request_id": request_id, "stage": "store", "webid": participant_id},
                )
                return _error_response(
                    status_code=502,
                    error="store_write_failed",
                    detail=f"catalog store write failed: {exc}",
                    stage="store",
                    request_id=request_id,
                )

            logger.info(
                "Solid push accepted and stored",
                extra={
                    "request_id": request_id,
                    "stage": "store",
                    "webid": participant_id,
                    "graph": graph_id,
                },
            )
            return {
                "accepted": True,
                "mode": "solid",
                "participant_id": participant_id,
                "graph": graph_id,
                "request_id": request_id,
            }

        return router
