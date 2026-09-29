# Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
"""DCAT serialization helpers adapted from the upstream Fuseki module."""

import os
from datetime import datetime
from urllib.parse import urlparse


def _is_http_url(value: str | None) -> bool:
    try:
        parsed = urlparse(value or "")
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except (TypeError, ValueError):
        return False


def _escape_literal(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _normalize_distribution_access_type(value: str | None) -> str:
    return "access" if value == "access" else "download"


def generate_dcat_dataset_ttl(dataset: dict) -> str:
    issued = dataset["issued"].isoformat() if isinstance(dataset["issued"], datetime) else dataset["issued"]
    modified = (
        dataset["modified"].isoformat()
        if isinstance(dataset["modified"], datetime)
        else dataset["modified"]
    )
    identifier = dataset["identifier"]
    base_uri = os.getenv("BASE_URI", "https://semantic-data-catalog.com")
    dataset_uri = f"{base_uri}/id/{identifier}"
    distribution_uri = f"{dataset_uri}/distribution"
    publisher_uri = f"{dataset_uri}/publisher"
    contact_uri = f"{dataset_uri}/contact"
    theme = dataset.get("theme")
    semantic_model_url = dataset.get("access_url_semantic_model")
    access_url_dataset = dataset.get("access_url_dataset")
    distribution_access_type = _normalize_distribution_access_type(
        dataset.get("distribution_access_type")
    )

    if not _is_http_url(access_url_dataset):
        raise ValueError("Dataset access URL must be a valid http(s) IRI.")
    if distribution_access_type == "access" and not dataset.get("is_public", True):
        raise ValueError("Public external links are currently supported only for public datasets.")

    dataset_lines = [
        f"<{dataset_uri}> a dcat:Dataset ;",
        f'    dct:title "{_escape_literal(dataset["title"])}" ;',
    ]

    description = dataset.get("description")
    if description:
        dataset_lines.append(f'    dct:description "{_escape_literal(description)}" ;')

    dataset_lines.extend(
        [
            f'    dct:issued "{_escape_literal(issued)}"^^xsd:dateTime ;',
            f'    dct:modified "{_escape_literal(modified)}"^^xsd:dateTime ;',
            f"    dct:publisher <{publisher_uri}> ;",
            f'    dct:accessRights "{"public" if dataset.get("is_public", True) else "restricted"}" ;',
            f"    dcat:contactPoint <{contact_uri}> ;",
            f"    dcat:distribution <{distribution_uri}> ;",
        ]
    )

    if theme:
        if _is_http_url(theme):
            dataset_lines.append(f"    dcat:theme <{theme}> ;")
        else:
            raise ValueError("Theme must be a valid http(s) IRI.")

    if semantic_model_url:
        if _is_http_url(semantic_model_url):
            dataset_lines.append(f"    dct:conformsTo <{semantic_model_url}> ;")
        else:
            raise ValueError("Semantic model URL must be a valid http(s) IRI.")

    dataset_lines[-1] = dataset_lines[-1].rstrip(" ;") + " ."

    distribution_lines = [
        f"<{distribution_uri}> a dcat:Distribution ;",
        f"    dcat:{'accessURL' if distribution_access_type == 'access' else 'downloadURL'} <{access_url_dataset}> ;",
    ]
    file_format = (dataset.get("file_format") or "").strip()
    if file_format:
        distribution_lines.append(f'    dcat:mediaType "{_escape_literal(file_format)}" ;')
    distribution_lines[-1] = distribution_lines[-1].rstrip(" ;") + " ."

    return "\n".join(
        [
            "@prefix dcat: <http://www.w3.org/ns/dcat#> .",
            "@prefix dct: <http://purl.org/dc/terms/> .",
            "@prefix foaf: <http://xmlns.com/foaf/0.1/> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix vcard: <http://www.w3.org/2006/vcard/ns#> .",
            "",
            *dataset_lines,
            "",
            *distribution_lines,
            "",
            f"<{publisher_uri}> a foaf:Agent ;",
            f'    foaf:name "{_escape_literal(dataset["publisher"])}" ;',
            f"    vcard:hasEmail <mailto:{dataset['contact_point']}> .",
            "",
            f"<{contact_uri}> a vcard:Kind ;",
            f"    vcard:hasEmail <mailto:{dataset['contact_point']}> .",
        ]
    )

