"""Opt-in source publication routes; transport is independent of source kind."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from rdflib import DCAT, DCTERMS, RDF, Graph
from starlette.concurrency import run_in_threadpool

from .errors import PublicationError
from .registry import FileRegistry
from .store import PublicationStore
from .validation import MAX_BODY_BYTES, PublicationValidator


class PublicationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request):
            try:
                return await handler(request)
            except PublicationError as exc:
                truncated = len(exc.detail) > 2048
                payload = {
                    "accepted": False,
                    "error": exc.code,
                    "detail": exc.detail[:2048],
                    "requestId": str(uuid4()),
                }
                if exc.errors is not None:
                    bounded = []
                    truncated = truncated or len(exc.errors) > 30
                    for error in exc.errors[:30]:
                        item = {}
                        for key, value in error.items():
                            text = str(value)
                            truncated = truncated or len(text) > 1024
                            item[key] = text[:1024]
                        bounded.append(item)
                    payload["errors"] = bounded
                if truncated:
                    payload["reportTruncated"] = True
                headers = {"Retry-After": "2"} if exc.status == 503 else None
                return JSONResponse(payload, status_code=exc.status, headers=headers)
            except sqlite3.Error:
                return JSONResponse(
                    {
                        "accepted": False,
                        "error": "store_unavailable",
                        "detail": "Publication store is unavailable; retry the identical request",
                        "requestId": str(uuid4()),
                    },
                    status_code=503,
                    headers={"Retry-After": "2"},
                )

        return wrapped


async def _bounded_body(request: Request) -> bytes:
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise PublicationError(400, "invalid_envelope", "Invalid Content-Length") from exc
    if declared > MAX_BODY_BYTES:
        raise PublicationError(413, "payload_too_large", "Publication envelope exceeds 2 MiB")
    size, parts = 0, []
    async for part in request.stream():
        size += len(part)
        if size > MAX_BODY_BYTES:
            raise PublicationError(413, "payload_too_large", "Publication envelope exceeds 2 MiB")
        parts.append(part)
    return b"".join(parts)


def _mutation_headers(request: Request) -> tuple[str, str]:
    revision = request.headers.get("Publication-If-Revision")
    if revision is None:
        raise PublicationError(428, "precondition_required", "Publication-If-Revision is required")
    if revision != "none" and not re.fullmatch(r'"r[1-9][0-9]*"', revision):
        raise PublicationError(
            400, "invalid_precondition", 'Revision must be none or a quoted token such as "r1"'
        )
    key = request.headers.get("Idempotency-Key")
    if key is None or not re.fullmatch(r"[\x21-\x7e]{1,200}", key):
        raise PublicationError(
            400,
            "idempotency_key_required",
            "Idempotency-Key must contain 1–200 visible ASCII characters",
        )
    return revision.strip('"'), key


def _fingerprint(request: Request, value) -> str:
    canonical = json.dumps(
        {
            "method": request.method,
            "path": request.url.path,
            "revision": request.headers["Publication-If-Revision"],
            "body": value,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"Not a JSON number: {value}")


def _receipt_response(result: tuple[int, dict]) -> JSONResponse:
    status, receipt = result
    return JSONResponse(
        receipt,
        status_code=status,
        headers={
            "Publication-Revision": f'"{receipt["revision"]}"',
            "Location": f"/v1/sources/{receipt['sourceId']}/catalog",
            "Cache-Control": "no-store",
        },
    )


class PublicationApi:
    def __init__(self, registry_file: str, database_path: str):
        self.registry = FileRegistry(registry_file)
        self.store = PublicationStore(database_path)
        self.validator = PublicationValidator()

    def status(self):
        self.registry.load()
        self.store.all()
        return {
            "mode": "shared",
            "operational": True,
            "dependencies": {"publication_registry": True, "publication_sqlite": True},
        }

    def routes(self) -> APIRouter:
        router = APIRouter(route_class=PublicationRoute)

        @router.get("/v1/profiles")
        def profiles():
            return self.validator.profiles()

        @router.get("/v1/sources/{source_id}/state")
        def state(source_id: str, request: Request):
            registry = self.registry.load()
            principal = registry.authenticate(request.headers.get("Authorization"))
            registry.authorize(principal, source_id, None)
            publication = self.store.get(source_id)
            if publication is None:
                raise PublicationError(
                    404, "source_unpublished", "Registered source has not published yet"
                )
            return JSONResponse(publication[0], headers={"Cache-Control": "no-store"})

        @router.put("/v1/sources/{source_id}/catalog")
        async def publish(source_id: str, request: Request):
            registry = self.registry.load()
            principal = registry.authenticate(request.headers.get("Authorization"))
            source = registry.authorize(principal, source_id, "publish")
            expected, key = _mutation_headers(request)
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                raise PublicationError(
                    415, "unsupported_media_type", "Publication envelope must be application/json"
                )
            body = await _bounded_body(request)
            try:
                envelope = json.loads(
                    body, object_pairs_hook=_json_object, parse_constant=_reject_json_constant
                )
                if not isinstance(envelope, dict):
                    raise TypeError("object required")
                fingerprint = _fingerprint(request, envelope)
            except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
                raise PublicationError(
                    400, "invalid_envelope", "Envelope must be a JSON object"
                ) from exc

            def apply():
                replay = self.store.replay(principal.id, source_id, "publish", key, fingerprint)
                if replay is not None:
                    return replay
                turtle, publication = self.validator.validate(envelope, source, registry)
                return self.store.mutate(
                    principal_id=principal.id,
                    source_id=source.id,
                    participant_id=source.participantId,
                    catalog_iri=source.catalogIri,
                    operation="publish",
                    key=key,
                    fingerprint=fingerprint,
                    expected_revision=expected,
                    publication=publication,
                    turtle=turtle,
                )

            return _receipt_response(await run_in_threadpool(apply))

        @router.delete("/v1/sources/{source_id}/catalog")
        async def withdraw(source_id: str, request: Request):
            registry = self.registry.load()
            principal = registry.authenticate(request.headers.get("Authorization"))
            source = registry.authorize(principal, source_id, "withdraw")
            expected, key = _mutation_headers(request)
            if await _bounded_body(request):
                raise PublicationError(400, "invalid_envelope", "Withdrawal requests have no body")
            fingerprint = _fingerprint(request, None)
            result = await run_in_threadpool(
                self.store.mutate,
                principal_id=principal.id,
                source_id=source.id,
                participant_id=source.participantId,
                catalog_iri=source.catalogIri,
                operation="withdraw",
                key=key,
                fingerprint=fingerprint,
                expected_revision=expected,
            )
            return _receipt_response(result)

        @router.get("/v1/sources/{source_id}/catalog")
        def catalog(source_id: str):
            registry = self.registry.load()
            publication = self.store.get(source_id)
            if publication is None or not registry.visible(publication[0]):
                raise PublicationError(
                    404, "catalog_not_found", "No active public catalog for this source"
                )
            return Response(
                publication[1],
                media_type="text/turtle",
                headers={
                    "Publication-Revision": f'"{publication[0]["revision"]}"',
                    "Cache-Control": "no-store",
                },
            )

        @router.get("/v1/datasets")
        def datasets():
            registry = self.registry.load()
            results = []
            for state, turtle in self.store.all():
                if not registry.visible(state):
                    continue
                source = registry.sources[state["sourceId"]]
                graph = Graph().parse(data=turtle, format="turtle")
                for dataset in graph.subjects(RDF.type, DCAT.Dataset):
                    results.append(
                        {
                            "datasetId": str(dataset),
                            "title": str(graph.value(dataset, DCTERMS.title) or ""),
                            "sourceId": source.id,
                            "sourceKind": source.kind,
                            "participantId": source.participantId,
                            "catalogIri": source.catalogIri,
                            "revision": state["revision"],
                            "publishedAt": state["updatedAt"],
                        }
                    )
            return JSONResponse(
                {
                    "datasets": sorted(
                        results, key=lambda item: (item["sourceId"], item["datasetId"])
                    )
                },
                headers={"Cache-Control": "no-store"},
            )

        return router


def publication_api_from_env() -> PublicationApi | None:
    registry = os.getenv("PUBLICATION_REGISTRY_FILE")
    database = os.getenv("PUBLICATION_DB_PATH")
    if not registry and not database:
        return None
    if not registry or not database:
        raise RuntimeError("Set both PUBLICATION_REGISTRY_FILE and PUBLICATION_DB_PATH")
    return PublicationApi(registry, database)
