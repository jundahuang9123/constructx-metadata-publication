# Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
"""SHACL validation helpers adapted from the upstream FastAPI backend."""

from pathlib import Path

from pyshacl import validate
from rdflib import RDF, Graph, Namespace

from core.interfaces.validation import ValidationGate
from core.interfaces.validation import ValidationResult
from core.shared.rdf import parse_rdf_payload

SH = Namespace("http://www.w3.org/ns/shacl#")


def default_shape_path() -> Path:
    return Path(__file__).resolve().parent / "shapes" / "sdcat-shape.ttl"


def _extract_errors(results_graph: Graph, results_text: str) -> list[str]:
    errors: list[str] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        messages = [str(value) for value in results_graph.objects(result, SH.resultMessage)]
        focus = next(results_graph.objects(result, SH.focusNode), None)
        path = next(results_graph.objects(result, SH.resultPath), None)
        prefix_parts = []
        if focus:
            prefix_parts.append(f"focus={focus}")
        if path:
            prefix_parts.append(f"path={path}")
        prefix = f"{', '.join(prefix_parts)}: " if prefix_parts else ""
        if messages:
            errors.extend(f"{prefix}{message}" for message in messages)
        elif prefix:
            errors.append(prefix.rstrip(": "))

    if errors:
        return errors

    return [line.strip() for line in results_text.splitlines() if line.strip()]


def validate_rdf(
    rdf_payload: str,
    *,
    shape_path: str | Path | None = None,
    content_type: str | None = None,
    format: str | None = None,
) -> ValidationResult:
    try:
        data_graph = parse_rdf_payload(rdf_payload, content_type=content_type, format=format)
    except Exception as exc:
        return ValidationResult(ok=False, errors=[f"RDF parse error: {exc}"])

    if len(data_graph) == 0:
        return ValidationResult(ok=False, errors=["RDF payload parsed successfully but contains no triples"])

    try:
        shape_graph = Graph()
        shape_graph.parse(str(shape_path or default_shape_path()), format="turtle")
        conforms, results_graph, results_text = validate(
            data_graph=data_graph,
            shacl_graph=shape_graph,
            inference="rdfs",
            debug=False,
        )
    except Exception as exc:
        return ValidationResult(ok=False, errors=[f"SHACL validation error: {exc}"])

    if conforms:
        return ValidationResult(ok=True)
    return ValidationResult(ok=False, errors=_extract_errors(results_graph, results_text))


class ShaclValidationGate(ValidationGate):
    def __init__(self, shape_path: str | Path | None = None) -> None:
        self.shape_path = shape_path or default_shape_path()

    def validate(self, rdf_payload: str, *, format: str | None = None) -> ValidationResult:
        return validate_rdf(rdf_payload, shape_path=self.shape_path, format=format)

