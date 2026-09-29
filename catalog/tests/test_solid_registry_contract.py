from pathlib import Path

import pytest

from modes.solid.registry_contract import RegistryContractError, load_registry_contract


def _write_contract(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "contract.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _minimal_contract(*, shape_type: str = "ldp-container-member-resources") -> str:
    return f"""
version: 1
name: test-contract
description: Test contract.
registry:
  url_env: SOLID_REGISTRY_URL
  rdf_format: auto
shape:
  type: {shape_type}
  container:
    member_resource_predicates:
      - http://www.w3.org/ns/ldp#contains
  member_resource:
    webid_predicates:
      - http://xmlns.com/foaf/0.1/member
fetch:
  follow_member_resources: true
  timeout_seconds: 10
matching:
  strategy: exact
  normalize:
    trim: true
    preserve_fragment: true
    lowercase_scheme_host: false
cache:
  ttl_seconds_env: SOLID_REGISTRY_CACHE_TTL_SECONDS
  default_ttl_seconds: 300
failure:
  fail_closed: true
  unregistered_status: 403
"""


def test_default_registry_contract_loads_successfully() -> None:
    contract = load_registry_contract()

    assert contract.version == 1
    assert contract.registry_url_env == "SOLID_REGISTRY_URL"
    assert contract.shape_type == "ldp-container-member-resources"
    assert contract.container_member_resource_predicates == (
        "http://www.w3.org/ns/ldp#contains",
    )
    assert contract.member_resource_webid_predicates == (
        "http://xmlns.com/foaf/0.1/member",
    )


def test_registry_contract_missing_required_field_fails_clearly(tmp_path: Path) -> None:
    path = _write_contract(
        tmp_path,
        _minimal_contract().replace(
            "  container:\n"
            "    member_resource_predicates:\n"
            "      - http://www.w3.org/ns/ldp#contains\n",
            "  container: {}\n",
        ),
    )

    with pytest.raises(RegistryContractError, match="member_resource_predicates"):
        load_registry_contract(path)


def test_registry_contract_unsupported_shape_type_fails_clearly(tmp_path: Path) -> None:
    path = _write_contract(tmp_path, _minimal_contract(shape_type="single-rdf-document"))

    with pytest.raises(
        RegistryContractError,
        match="Unsupported registry contract shape type: single-rdf-document",
    ):
        load_registry_contract(path)
