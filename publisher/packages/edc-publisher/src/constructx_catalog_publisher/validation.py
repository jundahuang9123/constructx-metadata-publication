"""Local profile and topology checks. The catalog validates again independently."""

from __future__ import annotations

import hashlib
from importlib.resources import files

from pyshacl import validate
from rdflib import DCAT, RDF, SH, Graph, URIRef

from .converter import iri


def profile_bytes() -> bytes:
    return files("constructx_catalog_publisher").joinpath("profile.ttl").read_bytes()


def profile_hash() -> dict:
    return {"algorithm": "sha256", "value": hashlib.sha256(profile_bytes()).hexdigest()}


def validate_graph(graph: Graph, root_iri: str) -> dict:
    root = iri(root_iri, "catalogIri")
    errors = []
    catalogs, datasets, distributions, services = set(), set(), set(), set()

    def check(node, kind):
        if not isinstance(node, URIRef):
            errors.append({"focusNode": str(node), "message": "DCAT resources need stable IRIs."})
        else:
            try:
                iri(str(node))
            except ValueError:
                errors.append({"focusNode": str(node), "message": "Resource IRI must be absolute."})
        if (node, RDF.type, kind) not in graph:
            errors.append({"focusNode": str(node), "message": f"Explicit {kind} type required."})

    check(root, DCAT.Catalog)
    pending = [root]
    while pending:
        catalog = pending.pop()
        if catalog in catalogs:
            continue
        catalogs.add(catalog)
        check(catalog, DCAT.Catalog)
        for child in graph.objects(catalog, DCAT.catalog):
            if not isinstance(child, URIRef):
                errors.append(
                    {"focusNode": str(child), "message": "Catalog references need stable IRIs."}
                )
            # External catalog references are permitted, but local descriptions need a type.
            if any(graph.triples((child, None, None))):
                pending.append(child)
        for dataset in graph.objects(catalog, DCAT.dataset):
            datasets.add(dataset)
            check(dataset, DCAT.Dataset)
    for dataset in datasets:
        for dist in graph.objects(dataset, DCAT.distribution):
            distributions.add(dist)
            check(dist, DCAT.Distribution)
    for dist in distributions:
        for service in graph.objects(dist, DCAT.accessService):
            services.add(service)
            check(service, DCAT.DataService)
    for kind, reachable in (
        (DCAT.Catalog, catalogs),
        (DCAT.Dataset, datasets),
        (DCAT.Distribution, distributions),
        (DCAT.DataService, services),
    ):
        for node in set(graph.subjects(RDF.type, kind)) - reachable:
            errors.append(
                {
                    "focusNode": str(node),
                    "message": "DCAT resource is disconnected from the registered root.",
                }
            )
    for predicate, parents in (
        (DCAT.catalog, catalogs),
        (DCAT.dataset, catalogs),
        (DCAT.distribution, datasets),
        (DCAT.accessService, distributions),
    ):
        if not set(graph.subjects(predicate, None)).issubset(parents):
            errors.append(
                {
                    "path": str(predicate),
                    "message": "Structural link is outside the catalog hierarchy.",
                }
            )
    shapes = Graph().parse(data=profile_bytes().decode(), format="turtle")
    conforms, report, _ = validate(
        graph,
        shacl_graph=shapes,
        inference="none",
        advanced=False,
        do_owl_imports=False,
        inplace=False,
    )
    for result in report.subjects(RDF.type, SH.ValidationResult):
        errors.append(
            {
                "focusNode": str(report.value(result, SH.focusNode) or ""),
                "path": str(report.value(result, SH.resultPath) or ""),
                "message": str(
                    report.value(result, SH.resultMessage) or "Profile validation failed."
                ),
            }
        )
    return {
        "conforms": bool(conforms) and not errors,
        "datasetCount": len(datasets),
        "errors": errors[:100],
        "truncated": len(errors) > 100,
        "profileShapeHash": profile_hash(),
    }
