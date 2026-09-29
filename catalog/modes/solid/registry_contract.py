"""Machine-readable Solid registry contract loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_CONTRACT_PATH = Path("config/solid-registry-contract.yaml")
SUPPORTED_SHAPE_TYPE = "ldp-container-member-resources"


class RegistryContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class SolidRegistryContract:
    version: int
    name: str
    description: str
    registry_url_env: str
    registry_rdf_format: str
    shape_type: str
    container_member_resource_predicates: tuple[str, ...]
    member_resource_webid_predicates: tuple[str, ...]
    fetch_follow_member_resources: bool
    fetch_timeout_seconds: float
    matching_strategy: str
    normalize_trim: bool
    normalize_preserve_fragment: bool
    normalize_lowercase_scheme_host: bool
    cache_ttl_seconds_env: str
    cache_default_ttl_seconds: float
    failure_fail_closed: bool
    failure_unregistered_status: int


def _resolve_contract_path(path: str | os.PathLike[str] | None = None) -> Path:
    raw_path = Path(
        path
        or os.getenv("SOLID_REGISTRY_CONTRACT_PATH")
        or DEFAULT_REGISTRY_CONTRACT_PATH
    )
    if raw_path.is_absolute():
        return raw_path

    cwd_path = Path.cwd() / raw_path
    if cwd_path.exists():
        return cwd_path

    project_path = Path(__file__).resolve().parents[2] / raw_path
    return project_path


def _mapping(value: Any, field_path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryContractError(f"Missing required registry contract field: {field_path}")
    return value


def _field(mapping: dict[str, Any], name: str, field_path: str) -> Any:
    if name not in mapping:
        raise RegistryContractError(
            f"Missing required registry contract field: {field_path}.{name}"
        )
    return mapping[name]


def _string(mapping: dict[str, Any], name: str, field_path: str) -> str:
    value = _field(mapping, name, field_path)
    if not isinstance(value, str) or not value.strip():
        raise RegistryContractError(f"Invalid registry contract field: {field_path}.{name}")
    return value.strip()


def _bool(mapping: dict[str, Any], name: str, field_path: str) -> bool:
    value = _field(mapping, name, field_path)
    if not isinstance(value, bool):
        raise RegistryContractError(f"Invalid registry contract field: {field_path}.{name}")
    return value


def _float(mapping: dict[str, Any], name: str, field_path: str) -> float:
    value = _field(mapping, name, field_path)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RegistryContractError(
            f"Invalid registry contract field: {field_path}.{name}"
        ) from exc


def _int(mapping: dict[str, Any], name: str, field_path: str) -> int:
    value = _field(mapping, name, field_path)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RegistryContractError(
            f"Invalid registry contract field: {field_path}.{name}"
        ) from exc


def _string_tuple(mapping: dict[str, Any], name: str, field_path: str) -> tuple[str, ...]:
    value = _field(mapping, name, field_path)
    if not isinstance(value, list):
        raise RegistryContractError(f"Invalid registry contract field: {field_path}.{name}")

    strings = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(strings) != len(value) or not strings:
        raise RegistryContractError(f"Invalid registry contract field: {field_path}.{name}")
    return strings


def load_registry_contract(path: str | os.PathLike[str] | None = None) -> SolidRegistryContract:
    contract_path = _resolve_contract_path(path)
    if not contract_path.exists():
        raise RegistryContractError(f"Solid registry contract file not found: {contract_path}")

    try:
        raw = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryContractError(
            f"Invalid Solid registry contract YAML: {contract_path}"
        ) from exc

    root = _mapping(raw, "<root>")
    registry = _mapping(_field(root, "registry", "<root>"), "registry")
    shape = _mapping(_field(root, "shape", "<root>"), "shape")
    container = _mapping(_field(shape, "container", "shape"), "shape.container")
    member_resource = _mapping(
        _field(shape, "member_resource", "shape"),
        "shape.member_resource",
    )
    fetch = _mapping(_field(root, "fetch", "<root>"), "fetch")
    matching = _mapping(_field(root, "matching", "<root>"), "matching")
    normalize = _mapping(_field(matching, "normalize", "matching"), "matching.normalize")
    cache = _mapping(_field(root, "cache", "<root>"), "cache")
    failure = _mapping(_field(root, "failure", "<root>"), "failure")

    shape_type = _string(shape, "type", "shape")
    if shape_type != SUPPORTED_SHAPE_TYPE:
        raise RegistryContractError(f"Unsupported registry contract shape type: {shape_type}")

    matching_strategy = _string(matching, "strategy", "matching")
    if matching_strategy != "exact":
        raise RegistryContractError(
            f"Unsupported registry contract matching strategy: {matching_strategy}"
        )

    return SolidRegistryContract(
        version=_int(root, "version", "<root>"),
        name=_string(root, "name", "<root>"),
        description=_string(root, "description", "<root>"),
        registry_url_env=_string(registry, "url_env", "registry"),
        registry_rdf_format=_string(registry, "rdf_format", "registry"),
        shape_type=shape_type,
        container_member_resource_predicates=_string_tuple(
            container,
            "member_resource_predicates",
            "shape.container",
        ),
        member_resource_webid_predicates=_string_tuple(
            member_resource,
            "webid_predicates",
            "shape.member_resource",
        ),
        fetch_follow_member_resources=_bool(fetch, "follow_member_resources", "fetch"),
        fetch_timeout_seconds=_float(fetch, "timeout_seconds", "fetch"),
        matching_strategy=matching_strategy,
        normalize_trim=_bool(normalize, "trim", "matching.normalize"),
        normalize_preserve_fragment=_bool(normalize, "preserve_fragment", "matching.normalize"),
        normalize_lowercase_scheme_host=_bool(
            normalize,
            "lowercase_scheme_host",
            "matching.normalize",
        ),
        cache_ttl_seconds_env=_string(cache, "ttl_seconds_env", "cache"),
        cache_default_ttl_seconds=_float(cache, "default_ttl_seconds", "cache"),
        failure_fail_closed=_bool(failure, "fail_closed", "failure"),
        failure_unregistered_status=_int(failure, "unregistered_status", "failure"),
    )
