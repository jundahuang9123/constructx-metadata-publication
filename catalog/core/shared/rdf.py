from __future__ import annotations

from rdflib import Graph


CONTENT_TYPE_TO_RDFLIB_FORMAT = {
    "application/ld+json": "json-ld",
    "application/json": "json-ld",
    "application/n-quads": "nquads",
    "application/n-triples": "nt",
    "application/rdf+xml": "xml",
    "application/trig": "trig",
    "application/x-turtle": "turtle",
    "text/n3": "n3",
    "text/turtle": "turtle",
}


def normalize_content_type(content_type: str | None) -> str:
    return (content_type or "text/turtle").split(";", 1)[0].strip().lower()


def guess_rdflib_format(content_type: str | None = None, explicit_format: str | None = None) -> str:
    if explicit_format:
        return explicit_format
    return CONTENT_TYPE_TO_RDFLIB_FORMAT.get(normalize_content_type(content_type), "turtle")


def parse_rdf_payload(
    rdf_payload: str,
    *,
    content_type: str | None = None,
    format: str | None = None,
) -> Graph:
    graph = Graph()
    graph.parse(data=rdf_payload, format=guess_rdflib_format(content_type, format))
    return graph


def serialize_rdf_to_turtle(
    rdf_payload: str,
    *,
    content_type: str | None = None,
    format: str | None = None,
) -> str:
    graph = parse_rdf_payload(rdf_payload, content_type=content_type, format=format)
    serialized = graph.serialize(format="turtle")
    return serialized.decode("utf-8") if isinstance(serialized, bytes) else serialized

