"""Explicit asset-property mapping; no payload downloads or backend-address publication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

from rdflib import DCAT, DCTERMS, RDF, Graph, Literal, Namespace, URIRef

from .inventory import asset_id

EDC = "https://w3id.org/edc/v0.0.1/ns/"
CX = Namespace("https://w3id.org/construct-dcat#")
PUB = Namespace("urn:constructx:publication:")
CONTEXT = {
    "@vocab": EDC,
    "edc": EDC,
    "dcat": str(DCAT),
    "dct": str(DCTERMS),
    "rdf": str(RDF),
    "cx": str(CX),
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
PROFILE_IRI = "urn:constructx:profile:publication-draft:0.1"


class MappingError(ValueError):
    pass


def iri(value: Any, label: str = "IRI") -> URIRef:
    if (
        not isinstance(value, str)
        or not urlsplit(value).scheme
        or re.search(r'[\s<>"{}|^`\\]', value)
    ):
        raise MappingError(f"{label} must be an absolute IRI.")
    return URIRef(value)


def safe_contexts(value: Any, pinned: dict, stack: tuple = ()) -> Any:
    """Replace explicitly pinned contexts, refusing network loads and imports."""
    if isinstance(value, list):
        return [safe_contexts(v, pinned, stack) for v in value]
    if isinstance(value, str):
        if value in stack or value not in pinned:
            raise MappingError("Remote JSON-LD context needs an explicit local pin in contexts.")
        context = pinned[value]
        if isinstance(context, dict) and "@context" in context:
            context = context["@context"]
        return safe_contexts(context, pinned, (*stack, value))
    if not isinstance(value, dict):
        raise MappingError("Only inline or explicitly pinned JSON-LD contexts are supported.")
    if "@import" in value or "@base" in value:
        raise MappingError("Context imports and relative base IRIs are not supported.")
    result = {}
    for key, definition in value.items():
        if isinstance(definition, dict) and "@context" in definition:
            definition = {
                **definition,
                "@context": safe_contexts(definition["@context"], pinned, stack),
            }
        result[key] = definition
    return result


def sanitize(value: Any, pinned: dict, stack: tuple = ()) -> Any:
    if isinstance(value, list):
        return [sanitize(v, pinned, stack) for v in value]
    if isinstance(value, dict):
        if "@import" in value or "@base" in value:
            raise MappingError("Context imports and relative base IRIs are not supported.")
        identifier = value.get("@id")
        if (
            isinstance(identifier, str)
            and not identifier.startswith("_:")
            and not urlsplit(identifier).scheme
        ):
            raise MappingError(
                "Metadata @id values must be absolute IRIs or blank-node identifiers."
            )
        return {
            k: safe_contexts(v, pinned, stack) if k == "@context" else sanitize(v, pinned, stack)
            for k, v in value.items()
        }
    return value


def context_parts(context: Any) -> list[dict]:
    if isinstance(context, list):
        return [part for entry in context for part in context_parts(entry)]
    if not isinstance(context, dict):
        raise MappingError("Context must resolve to inline definitions.")
    return [context]


def flatten_context(context: Any, result: dict | None = None) -> dict:
    result = dict(result or {})
    for part in context if isinstance(context, list) else [context]:
        if not isinstance(part, dict):
            raise MappingError("Context must resolve to inline definitions.")
        result.update(part)
    return result


def expand(term: str, context: dict, seen: tuple = ()) -> str:
    if term in seen:
        raise MappingError("Cyclic JSON-LD term definition.")
    definition = context.get(term)
    if isinstance(definition, dict):
        definition = definition.get("@id")
    if isinstance(definition, str) and definition != term:
        return expand(definition, context, (*seen, term))
    if ":" in term:
        prefix, rest = term.split(":", 1)
        prefix_definition = context.get(prefix)
        if isinstance(prefix_definition, dict):
            prefix_definition = prefix_definition.get("@id")
        if isinstance(prefix_definition, str):
            return prefix_definition + rest
        return term
    return str(context.get("@vocab", "")) + term


def unwrap(value: Any) -> Any:
    if isinstance(value, list) and len(value) == 1:
        return unwrap(value[0])
    if isinstance(value, dict) and "@value" in value:
        return value["@value"]
    return value


@dataclass
class ConvertedCatalog:
    graph: Graph
    audit: dict


def convert_assets(assets: list[dict], config: dict) -> ConvertedCatalog:
    root = iri(config.get("catalogIri"), "catalogIri")
    source_id = config.get("sourceId")
    if not isinstance(source_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", source_id
    ):
        raise MappingError("sourceId must be a simple stable identifier (letters, digits, . _ -).")
    if not isinstance(config.get("title"), str) or not config["title"].strip():
        raise MappingError("Provide a catalog title.")
    publisher = iri(config.get("publisherIri"), "publisherIri")
    endpoint = iri(config.get("dspEndpoint"), "dspEndpoint")
    if urlsplit(str(endpoint)).scheme not in {"http", "https"}:
        raise MappingError("dspEndpoint must use HTTP(S).")
    selection = config.get("selection", {})
    all_assets = selection.get("allAssets") is True
    selected_ids = selection.get("assetIds")
    if all_assets == (selected_ids is not None):
        raise MappingError("Choose selection.assetIds OR explicitly set selection.allAssets=true.")
    if selected_ids is not None and (
        not isinstance(selected_ids, list) or any(not isinstance(s, str) for s in selected_ids)
    ):
        raise MappingError("selection.assetIds must be a list of identifiers.")
    allowed = config.get("approvedProperties")
    if not isinstance(allowed, list) or any(not isinstance(s, str) for s in allowed):
        raise MappingError("Provide approvedProperties as an explicit list of predicate IRIs.")
    allowed = {str(iri(p, "approved property")) for p in allowed}
    forbidden = {EDC + "privateProperties", EDC + "dataAddress"}
    if allowed & forbidden:
        raise MappingError(
            "Private properties and backend data addresses cannot be approved fields."
        )
    pinned = config.get("contexts", {})
    base_context = [CONTEXT, safe_contexts(config.get("context", {}), pinned)]
    records: dict[str, dict] = {}
    for asset in assets:
        identifier = asset_id(asset)
        if identifier in records:
            raise MappingError("Duplicate asset identifiers in input.")
        records[identifier] = asset
    if selected_ids is not None and set(selected_ids) - records.keys():
        raise MappingError(
            "One or more explicitly selected assets are absent; refusing replacement."
        )
    selected = sorted(records) if all_assets else sorted(set(selected_ids))
    graph = Graph()
    for prefix, namespace in (("dcat", DCAT), ("dct", DCTERMS), ("cx", CX), ("pub", PUB)):
        graph.bind(prefix, namespace)
    graph.add((root, RDF.type, DCAT.Catalog))
    graph.add((root, DCTERMS.title, Literal(config["title"])))
    graph.add((root, DCTERMS.publisher, publisher))
    graph.add((root, PUB.sourceId, Literal(source_id)))
    if config.get("description"):
        graph.add((root, DCTERMS.description, Literal(config["description"])))
    catalog_ids = {str(root)}
    for cat in config.get("catalogs", []):
        node = iri(cat["id"], "subcatalog ID")
        if str(node) in catalog_ids:
            raise MappingError("Catalog identifiers must be unique.")
        catalog_ids.add(str(node))
        graph.add((node, RDF.type, DCAT.Catalog))
        graph.add((node, DCTERMS.title, Literal(cat["title"])))
        graph.add((iri(cat.get("parent", str(root))), DCAT.catalog, node))
    if any(str(s) not in catalog_ids for s in graph.subjects(DCAT.catalog, None)):
        raise MappingError("A subcatalog parent is not declared.")
    service = URIRef(str(root).rstrip("/") + "/service")
    audit = {
        "sourceId": source_id,
        "inputAssetCount": len(records),
        "selectedAssetCount": len(selected),
        "omittedAssetCount": len(records) - len(selected),
        "mappings": [],
        "excludedPropertyCount": 0,
        "warnings": [],
    }
    dataset_iris: set[str] = set()
    for identifier in selected:
        asset = records[identifier]
        contexts = base_context + (
            [safe_contexts(asset["@context"], pinned)] if "@context" in asset else []
        )
        contexts = context_parts(contexts)
        context = flatten_context(contexts)
        properties = next(
            (v for k, v in asset.items() if expand(k, context) == EDC + "properties"), None
        )
        properties = unwrap(properties)
        if not isinstance(properties, dict):
            raise MappingError("Asset requires an EDC properties object.")
        overrides = config.get("assetOverrides", {}).get(identifier, {})
        dataset = iri(
            overrides.get(
                "datasetIri", str(root).rstrip("/") + "/dataset/" + quote(identifier, safe="")
            )
        )
        if str(dataset) in dataset_iris or str(dataset) in catalog_ids:
            raise MappingError("Dataset identifiers must be distinct from each other and catalogs.")
        dataset_iris.add(str(dataset))
        document: dict = {"@context": contexts, "@id": str(dataset), "@type": str(DCAT.Dataset)}
        core_values = {}
        core_keys = {}
        for key, value in properties.items():
            predicate = expand(key, context)
            core_targets = {
                EDC + "name": str(DCTERMS.title),
                EDC + "description": str(DCTERMS.description),
                EDC + "contenttype": str(DCAT.mediaType),
            }
            if predicate in core_targets and (
                predicate in allowed or core_targets[predicate] in allowed
            ):
                core_values[predicate] = sanitize(value, pinned)
                core_keys[predicate] = key
            if predicate in allowed and not key.startswith("@"):
                document[key] = sanitize(value, pinned)
                audit["mappings"].append(
                    {"assetId": identifier, "from": predicate, "to": predicate}
                )
            elif predicate not in core_values:
                audit["excludedPropertyCount"] += 1
        try:
            graph.parse(data=json.dumps(document), format="json-ld")
        except MappingError:
            raise
        except Exception as exc:
            raise MappingError("Approved asset properties are not valid inline JSON-LD.") from exc
        for src, dest in (
            (EDC + "name", DCTERMS.title),
            (EDC + "description", DCTERMS.description),
        ):
            if (dataset, dest, None) not in graph and src in core_values:
                value = core_values[src]
                original = {"@context": contexts, "@id": str(dataset), core_keys[src]: value}
                parsed = Graph().parse(data=json.dumps(original), format="json-ld")
                for obj in parsed.objects(dataset, URIRef(src)):
                    graph.add((dataset, dest, obj))
                for subject, predicate, obj in parsed:
                    if subject != dataset:
                        graph.add((subject, predicate, obj))
                audit["mappings"].append({"assetId": identifier, "from": src, "to": str(dest)})
        # Overrides are explicit provider-authored metadata, separately identified in the audit.
        if overrides.get("properties"):
            override_doc = {"@context": contexts, "@id": str(dataset)}
            for key, value in overrides["properties"].items():
                predicate = expand(key, context)
                if predicate not in allowed or key.startswith("@"):
                    raise MappingError("Override predicates must be explicitly approved.")
                graph.remove((dataset, URIRef(predicate), None))
                override_doc[key] = sanitize(value, pinned)
            graph.parse(data=json.dumps(override_doc), format="json-ld")
            audit["mappings"].append(
                {
                    "assetId": identifier,
                    "from": "provider configuration",
                    "to": "dataset properties",
                }
            )
        for key, predicate in (("title", DCTERMS.title), ("description", DCTERMS.description)):
            if key in overrides:
                graph.set((dataset, predicate, Literal(overrides[key])))
        graph.add((dataset, RDF.type, DCAT.Dataset))
        graph.add((dataset, PUB.connectorAssetId, Literal(identifier)))
        parent = str(overrides.get("catalogIri", root))
        if parent not in catalog_ids:
            raise MappingError("Dataset catalogIri is not a configured catalog.")
        graph.add((URIRef(parent), DCAT.dataset, dataset))
        distributions = overrides.get("distributions")
        if distributions is not None:
            if list(graph.objects(dataset, DCAT.distribution)):
                raise MappingError("Choose asset-supplied or configured distributions, not both.")
            if not isinstance(distributions, list):
                raise MappingError("distributions must be a list.")
            audit["mappings"].append(
                {
                    "assetId": identifier,
                    "from": "provider configuration",
                    "to": "distribution descriptions",
                }
            )
        elif not list(graph.objects(dataset, DCAT.distribution)):
            distributions = [{"id": str(dataset).rstrip("/") + "/distribution"}]
            content_type = unwrap(core_values.get(EDC + "contenttype"))
            if content_type:
                distributions[0]["mediaType"] = content_type
            audit["mappings"].append(
                {
                    "assetId": identifier,
                    "from": "configured DSP endpoint",
                    "to": "access service and distribution",
                }
            )
        for dist in distributions or []:
            node = iri(dist.get("id"), "distribution ID")
            graph.add((dataset, DCAT.distribution, node))
            graph.add((node, RDF.type, DCAT.Distribution))
            graph.add((node, DCAT.accessURL, iri(dist.get("accessURL", str(endpoint)))))
            graph.add((node, DCAT.accessService, service))
            graph.add((service, RDF.type, DCAT.DataService))
            graph.add((service, DCAT.endpointURL, endpoint))
            graph.add((service, DCTERMS.title, Literal("Construct-X connector access service")))
            if dist.get("mediaType"):
                media = dist["mediaType"]
                if isinstance(media, str) and re.fullmatch(
                    r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", media
                ):
                    media = "https://www.iana.org/assignments/media-types/" + media
                graph.add((node, DCAT.mediaType, iri(media, "mediaType")))
            for key, predicate in (
                ("formatIri", DCTERMS.format),
                ("conformsTo", DCTERMS.conformsTo),
            ):
                if dist.get(key):
                    graph.add((node, predicate, iri(dist[key], key)))
        if not list(graph.objects(dataset, CX.describesAssetType)):
            audit["warnings"].append(
                {
                    "assetId": identifier,
                    "message": "No construction asset-type anchor supplied; provisional profile does not require it.",
                }
            )
    if any(str(predicate) in forbidden for _, predicate, _ in graph):
        raise MappingError(
            "Approved metadata contains a nested private/backend configuration predicate."
        )
    audit["tripleCount"] = len(graph)
    audit["mappingConfigSha256"] = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    return ConvertedCatalog(graph, audit)
