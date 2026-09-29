"""Server-owned provisional profile and independent graph admission checks."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pyshacl import validate
from rdflib import DCAT, RDF, Graph, Namespace, URIRef

from .errors import PublicationError
from .registry import Registry, Source

PROFILE_IRI = "urn:constructx:profile:publication-draft:0.1"
MAX_BODY_BYTES = 2 * 1024 * 1024
SH = Namespace("http://www.w3.org/ns/shacl#")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ShapeHash(Model):
    algorithm: Literal["sha256"]
    value: str = Field(pattern=r"^[a-f0-9]{64}$")


class Harvest(Model):
    complete: bool
    datasetCount: int = Field(ge=0)
    allowEmpty: bool = False
    startedAt: str
    finishedAt: str
    sourceRevision: str | None = None
    verification: dict | None = None


class RdfPayload(Model):
    mediaType: str
    content: str


class Envelope(Model):
    catalogIri: str
    profileIri: str
    profileShapeHash: ShapeHash
    audience: str
    harvest: Harvest
    rdf: RdfPayload


def _stable_iri(node) -> bool:
    try:
        return (
            isinstance(node, URIRef)
            and bool(urlsplit(str(node)).scheme)
            and not re.search(r'[<>"{}|^`\\\s]', str(node))
        )
    except ValueError:
        return False


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result
    except (ValueError, OverflowError) as exc:
        raise PublicationError(
            400, "invalid_envelope", "Harvest timestamps must include a timezone"
        ) from exc


def check_topology(graph: Graph, root: URIRef, registered_catalogs: set[str]) -> int:
    def fail(detail):
        raise PublicationError(422, "graph_scope_invalid", detail)

    def require(node, kind):
        if not _stable_iri(node) or (node, RDF.type, kind) not in graph:
            fail(f"A linked {kind} must have a stable IRI and explicit type: {node}")

    subjects = set(graph.subjects())
    if any(URIRef(iri) in subjects for iri in registered_catalogs - {str(root)}):
        fail("The graph describes another registered source's root catalog")
    require(root, DCAT.Catalog)
    catalogs, datasets, distributions, services = set(), set(), set(), set()
    pending = [root]
    while pending:
        catalog = pending.pop()
        if catalog in catalogs:
            continue
        require(catalog, DCAT.Catalog)
        catalogs.add(catalog)
        for child in graph.objects(catalog, DCAT.catalog):
            if not _stable_iri(child):
                fail("Catalog references must be stable IRIs")
            if child in subjects:
                require(child, DCAT.Catalog)
                pending.append(child)
        for dataset in graph.objects(catalog, DCAT.dataset):
            require(dataset, DCAT.Dataset)
            datasets.add(dataset)
    for dataset in datasets:
        for distribution in graph.objects(dataset, DCAT.distribution):
            require(distribution, DCAT.Distribution)
            distributions.add(distribution)
    for distribution in distributions:
        for service in graph.objects(distribution, DCAT.accessService):
            require(service, DCAT.DataService)
            services.add(service)
    for kind, reachable in (
        (DCAT.Catalog, catalogs),
        (DCAT.Dataset, datasets),
        (DCAT.Distribution, distributions),
        (DCAT.DataService, services),
    ):
        if set(graph.subjects(RDF.type, kind)) != reachable:
            fail(f"Every described {kind} must be reachable from the registered root")
    for predicate, parents in (
        (DCAT.catalog, catalogs),
        (DCAT.dataset, catalogs),
        (DCAT.distribution, datasets),
        (DCAT.accessService, distributions),
    ):
        if not set(graph.subjects(predicate, None)).issubset(parents):
            fail(f"A {predicate} link is attached to a node outside the catalog hierarchy")
    return len(datasets)


class PublicationValidator:
    def __init__(self):
        self.shape_bytes = Path(__file__).with_name("profile.ttl").read_bytes()
        self.shape_hash = {
            "algorithm": "sha256",
            "value": hashlib.sha256(self.shape_bytes).hexdigest(),
        }
        self.shapes = Graph().parse(data=self.shape_bytes.decode("utf-8"), format="turtle")

    def profiles(self) -> dict:
        return {
            "profiles": [
                {
                    "profileIri": PROFILE_IRI,
                    "profileShapeHash": self.shape_hash,
                    "rdf": {
                        "mediaType": "text/turtle",
                        "content": self.shape_bytes.decode("utf-8"),
                    },
                    "validation": {"inference": "none", "imports": False, "topologyChecks": True},
                }
            ],
            "limits": {"maxEnvelopeBytes": MAX_BODY_BYTES, "rdfMediaTypes": ["text/turtle"]},
        }

    def validate(self, raw: dict, source: Source, registry: Registry) -> tuple[str, dict]:
        try:
            envelope = Envelope.model_validate(raw)
        except ValidationError as exc:
            errors = [
                {"path": ".".join(map(str, item["loc"])), "message": item["msg"]}
                for item in exc.errors()[:31]
            ]
            raise PublicationError(
                400, "invalid_envelope", "Invalid publication envelope", errors
            ) from exc
        if envelope.catalogIri != source.catalogIri:
            raise PublicationError(
                422, "graph_scope_invalid", "Catalog IRI does not match the source registry"
            )
        if envelope.profileIri != PROFILE_IRI:
            raise PublicationError(
                409, "profile_version_conflict", "Unsupported publication profile"
            )
        if envelope.profileShapeHash.model_dump() != self.shape_hash:
            raise PublicationError(
                409,
                "profile_hash_conflict",
                "Shape artifact hash does not match the registered version",
            )
        if envelope.audience != "public":
            raise PublicationError(
                403, "audience_forbidden", "This receiver publishes public metadata only"
            )
        if envelope.rdf.mediaType != "text/turtle":
            raise PublicationError(
                415, "unsupported_media_type", "This initial receiver accepts text/turtle RDF only"
            )
        if not envelope.harvest.complete:
            raise PublicationError(
                422, "incomplete_harvest", "Incomplete harvest cannot replace a publication"
            )
        if _timestamp(envelope.harvest.startedAt) > _timestamp(envelope.harvest.finishedAt):
            raise PublicationError(400, "invalid_envelope", "Harvest finishedAt precedes startedAt")
        try:
            graph = Graph().parse(
                data=envelope.rdf.content, format="turtle", publicID=source.catalogIri
            )
        except Exception as exc:
            raise PublicationError(400, "invalid_rdf", "RDF is not valid Turtle") from exc
        count = check_topology(
            graph, URIRef(source.catalogIri), {s.catalogIri for s in registry.sources.values()}
        )
        if count != envelope.harvest.datasetCount:
            raise PublicationError(
                422,
                "graph_scope_invalid",
                "Declared dataset count does not match the reachable graph",
            )
        if count == 0 and not envelope.harvest.allowEmpty:
            raise PublicationError(
                422, "empty_not_confirmed", "An empty snapshot requires harvest.allowEmpty=true"
            )
        conforms, report, _ = validate(
            graph,
            shacl_graph=self.shapes,
            inference="none",
            do_owl_imports=False,
            advanced=False,
            js=False,
        )
        if not conforms:
            errors = [
                {
                    "focusNode": str(report.value(node, SH.focusNode) or ""),
                    "path": str(report.value(node, SH.resultPath) or ""),
                    "message": str(
                        report.value(node, SH.resultMessage) or "Shape constraint failed"
                    ),
                }
                for node in list(report.subjects(RDF.type, SH.ValidationResult))[:31]
            ]
            raise PublicationError(
                422, "profile_invalid", "Graph does not conform to the provisional profile", errors
            )
        publication = {
            "profileIri": PROFILE_IRI,
            "profileShapeHash": self.shape_hash,
            "datasetCount": count,
            "harvest": envelope.harvest.model_dump(exclude_none=True),
        }
        return graph.serialize(format="turtle"), publication
