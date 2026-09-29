from core.shared.shacl_validate import ShaclValidationGate, validate_rdf
from tests.fixtures import INVALID_SHACL_TURTLE, VALID_TURTLE


def test_validate_rdf_accepts_conformant_dcat() -> None:
    result = validate_rdf(VALID_TURTLE, format="turtle")

    assert result.ok
    assert result.errors == []


def test_validate_rdf_rejects_nonconformant_dcat() -> None:
    result = validate_rdf(INVALID_SHACL_TURTLE, format="turtle")

    assert not result.ok
    assert result.errors


def test_validate_rdf_rejects_invalid_rdf() -> None:
    result = validate_rdf("this is not valid RDF", format="turtle")

    assert not result.ok
    assert "RDF parse error" in result.errors[0]


def test_shacl_validation_gate_delegates_to_validator() -> None:
    gate = ShaclValidationGate()

    assert gate.validate(VALID_TURTLE, format="turtle").ok

