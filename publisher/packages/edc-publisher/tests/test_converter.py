"""Semantic preservation and disclosure-boundary checks using synthetic assets."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from rdflib import DCAT, DCTERMS, RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic

from constructx_catalog_publisher.converter import (
    CX,
    EDC,
    PUB,
    MappingError,
    convert_assets,
)
from constructx_catalog_publisher.validation import validate_graph

ROOT = "https://catalog.example/sources/connector-a"
ENDPOINT = "https://connector.example/dsp/2025-1"
EX = Namespace("https://example.org/metadata/")


def config():
    return {
        "sourceId": "connector-a",
        "catalogIri": ROOT,
        "title": "Connector A catalog",
        "publisherIri": "https://provider.example/organization",
        "dspEndpoint": ENDPOINT,
        "selection": {"allAssets": True},
        "approvedProperties": [EDC + "name", EDC + "description", EDC + "contenttype"],
    }


def asset(identifier="asphalt-a", **properties):
    return {
        "@context": {"@vocab": EDC},
        "@id": identifier,
        "properties": {
            "name": "Asphalt declaration",
            "contenttype": "application/json",
            **properties,
        },
        "privateProperties": {"internalNote": "SECRET-INTERNAL-NOTE"},
        "dataAddress": {
            "type": "HttpData",
            "baseUrl": "http://private-backend:8080/secret-data",
            "authKey": "Authorization",
            "authCode": "SECRET-BACKEND-TOKEN",
        },
    }


def dataset_node(graph: Graph, identifier="asphalt-a"):
    return graph.value(predicate=PUB.connectorAssetId, object=Literal(identifier))


class ConverterTests(unittest.TestCase):
    def test_minimal_compact_asset_maps_core_fields_and_public_access_service(self):
        converted = convert_assets([asset(description="Example supplied description")], config())
        graph = converted.graph
        dataset = dataset_node(graph)
        self.assertIn((URIRef(ROOT), DCAT.dataset, dataset), graph)
        self.assertIn((dataset, RDF.type, DCAT.Dataset), graph)
        self.assertIn((dataset, DCTERMS.title, Literal("Asphalt declaration")), graph)
        self.assertIn(
            (dataset, DCTERMS.description, Literal("Example supplied description")), graph
        )
        distribution = graph.value(dataset, DCAT.distribution)
        self.assertIn((distribution, DCAT.accessURL, URIRef(ENDPOINT)), graph)
        self.assertIn(
            (
                distribution,
                DCAT.mediaType,
                URIRef("https://www.iana.org/assignments/media-types/application/json"),
            ),
            graph,
        )
        service = graph.value(distribution, DCAT.accessService)
        self.assertIn((service, DCAT.endpointURL, URIRef(ENDPOINT)), graph)
        self.assertTrue(validate_graph(graph, ROOT)["conforms"])
        self.assertEqual(converted.audit["inputAssetCount"], 1)
        self.assertEqual(converted.audit["selectedAssetCount"], 1)

    def test_expanded_jsonld_asset_preserves_language_and_custom_resource(self):
        record = {
            "@id": "expanded-a",
            EDC + "properties": [
                {
                    EDC + "name": [{"@value": "Asphaltprodukt", "@language": "de"}],
                    EDC + "contenttype": [{"@value": "application/json"}],
                    str(CX.describesAssetType): [{"@id": "https://example.org/products/Asphalt"}],
                }
            ],
        }
        settings = config()
        settings["approvedProperties"].append(str(CX.describesAssetType))
        converted = convert_assets([record], settings)
        dataset = dataset_node(converted.graph, "expanded-a")
        self.assertIn(
            (dataset, DCTERMS.title, Literal("Asphaltprodukt", lang="de")), converted.graph
        )
        self.assertIn(
            (dataset, CX.describesAssetType, URIRef("https://example.org/products/Asphalt")),
            converted.graph,
        )
        self.assertEqual(converted.audit["warnings"], [])
        self.assertTrue(validate_graph(converted.graph, ROOT)["conforms"])

    def test_core_mapping_preserves_context_defined_language_containers_and_datatypes(self):
        settings = config()
        record = asset(
            name={"en": "Road material", "de": "Straßenmaterial"},
            description="<p>Public description</p>",
        )
        record["@context"] = {
            "@vocab": EDC,
            "name": {"@id": EDC + "name", "@container": "@language"},
            "description": {"@id": EDC + "description", "@type": str(RDF.HTML)},
        }
        graph = convert_assets([record], settings).graph
        dataset = dataset_node(graph)
        self.assertEqual(
            set(graph.objects(dataset, DCTERMS.title)),
            {
                Literal("Road material", lang="en"),
                Literal("Straßenmaterial", lang="de"),
            },
        )
        self.assertIn(
            (dataset, DCTERMS.description, Literal("<p>Public description</p>", datatype=RDF.HTML)),
            graph,
        )
        self.assertTrue(validate_graph(graph, ROOT)["conforms"])

    def test_approved_custom_properties_preserve_language_datatype_and_nested_description(self):
        settings = config()
        settings["context"] = {"ex": str(EX)}
        settings["approvedProperties"] += [str(DCTERMS.title), str(EX.mass), str(EX.subject)]
        record = asset(
            **{
                "dct:title": [
                    {"@value": "Road material", "@language": "en"},
                    {"@value": "Straßenmaterial", "@language": "de"},
                ],
                "ex:mass": {"@value": "1.25", "@type": "xsd:decimal"},
                "ex:subject": {
                    "@id": "https://example.org/materials/asphalt",
                    "dct:title": {"@value": "Asphalt", "@language": "en"},
                },
                "ex:unapproved": "PRIVATE-CUSTOM-PROPERTY",
            }
        )
        converted = convert_assets([record], settings)
        dataset = dataset_node(converted.graph)
        self.assertEqual(
            set(converted.graph.objects(dataset, DCTERMS.title)),
            {
                Literal("Road material", lang="en"),
                Literal("Straßenmaterial", lang="de"),
            },
        )
        self.assertIn((dataset, EX.mass, Literal("1.25", datatype=XSD.decimal)), converted.graph)
        subject = URIRef("https://example.org/materials/asphalt")
        self.assertIn((dataset, EX.subject, subject), converted.graph)
        self.assertIn((subject, DCTERMS.title, Literal("Asphalt", lang="en")), converted.graph)
        self.assertNotIn("PRIVATE-CUSTOM-PROPERTY", converted.graph.serialize(format="turtle"))

    def test_private_properties_and_backend_addresses_never_appear(self):
        converted = convert_assets([asset()], config())
        serialized = converted.graph.serialize(format="turtle")
        for private in (
            "SECRET-INTERNAL-NOTE",
            "private-backend",
            "secret-data",
            "SECRET-BACKEND-TOKEN",
            "authCode",
        ):
            self.assertNotIn(private, serialized)
            self.assertNotIn(private, str(converted.audit))
        for forbidden in (EDC + "privateProperties", EDC + "dataAddress"):
            settings = config()
            settings["approvedProperties"].append(forbidden)
            with self.assertRaises(MappingError):
                convert_assets([asset()], settings)

    def test_core_field_mappings_require_source_or_destination_approval(self):
        settings = config()
        settings["approvedProperties"] = []
        record = asset(description="UNAPPROVED-DESCRIPTION")
        converted = convert_assets([record], settings)
        dataset = dataset_node(converted.graph)
        self.assertEqual(list(converted.graph.objects(dataset, DCTERMS.title)), [])
        self.assertEqual(list(converted.graph.objects(dataset, DCTERMS.description)), [])
        self.assertEqual(list(converted.graph.triples((None, DCAT.mediaType, None))), [])
        self.assertNotIn("UNAPPROVED-DESCRIPTION", converted.graph.serialize(format="turtle"))
        settings["approvedProperties"] = [
            str(DCTERMS.title),
            str(DCTERMS.description),
            str(DCAT.mediaType),
        ]
        converted = convert_assets([record], settings)
        dataset = dataset_node(converted.graph)
        self.assertIn((dataset, DCTERMS.title, Literal("Asphalt declaration")), converted.graph)
        self.assertIn(
            (dataset, DCTERMS.description, Literal("UNAPPROVED-DESCRIPTION")), converted.graph
        )
        self.assertEqual(len(list(converted.graph.triples((None, DCAT.mediaType, None)))), 1)
        self.assertNotIn((dataset, URIRef(EDC + "name"), None), converted.graph)

    def test_selection_omits_unselected_assets_and_missing_selected_asset_aborts(self):
        settings = config()
        settings["selection"] = {"assetIds": ["chosen"]}
        converted = convert_assets([asset("chosen"), asset("unselected")], settings)
        self.assertEqual(
            set(converted.graph.objects(None, PUB.connectorAssetId)), {Literal("chosen")}
        )
        self.assertEqual(converted.audit["omittedAssetCount"], 1)
        self.assertNotIn("unselected", converted.graph.serialize(format="turtle"))
        with self.assertRaisesRegex(MappingError, "absent"):
            convert_assets([asset("unselected")], settings)

    def test_selection_requires_explicit_choice(self):
        for selection in ({}, {"allAssets": False}, {"allAssets": True, "assetIds": ["asphalt-a"]}):
            settings = config()
            settings["selection"] = selection
            with self.subTest(selection=selection), self.assertRaises(MappingError):
                convert_assets([asset()], settings)

    def test_nested_catalogs_and_multiple_provider_configured_distributions(self):
        settings = config()
        parent, child = ROOT + "/materials", ROOT + "/materials/asphalt"
        settings["catalogs"] = [
            {"id": parent, "title": "Materials"},
            {"id": child, "parent": parent, "title": "Asphalt"},
        ]
        settings["assetOverrides"] = {
            "asphalt-a": {
                "catalogIri": child,
                "distributions": [
                    {"id": ROOT + "/distribution/json", "mediaType": "application/json"},
                    {
                        "id": ROOT + "/distribution/turtle",
                        "mediaType": "text/turtle",
                        "conformsTo": "https://example.org/schema/Asphalt",
                    },
                ],
            }
        }
        graph = convert_assets([asset()], settings).graph
        dataset = dataset_node(graph)
        self.assertIn((URIRef(ROOT), DCAT.catalog, URIRef(parent)), graph)
        self.assertIn((URIRef(parent), DCAT.catalog, URIRef(child)), graph)
        self.assertIn((URIRef(child), DCAT.dataset, dataset), graph)
        self.assertEqual(len(list(graph.objects(dataset, DCAT.distribution))), 2)
        self.assertIn(
            (
                URIRef(ROOT + "/distribution/turtle"),
                DCTERMS.conformsTo,
                URIRef("https://example.org/schema/Asphalt"),
            ),
            graph,
        )
        self.assertTrue(validate_graph(graph, ROOT)["conforms"])

    def test_asset_supplied_distributions_and_services_are_preserved(self):
        settings = config()
        settings["approvedProperties"].append(str(DCAT.distribution))
        distributions = []
        for suffix in ("json", "rdf"):
            distributions.append(
                {
                    "@id": "https://provider.example/representations/" + suffix,
                    "@type": "dcat:Distribution",
                    "dcat:accessURL": {"@id": ENDPOINT},
                    "dcat:accessService": {
                        "@id": "https://provider.example/services/dsp",
                        "@type": "dcat:DataService",
                        "dcat:endpointURL": {"@id": ENDPOINT},
                    },
                }
            )
        graph = convert_assets([asset(**{"dcat:distribution": distributions})], settings).graph
        dataset = dataset_node(graph)
        self.assertEqual(
            set(graph.objects(dataset, DCAT.distribution)),
            {
                URIRef("https://provider.example/representations/json"),
                URIRef("https://provider.example/representations/rdf"),
            },
        )
        self.assertEqual(
            set(graph.subjects(RDF.type, DCAT.DataService)),
            {URIRef("https://provider.example/services/dsp")},
        )
        self.assertTrue(validate_graph(graph, ROOT)["conforms"])

    def test_identifiers_and_graph_are_stable_across_input_order(self):
        records = [asset("a/b : ü"), asset("second")]
        first = convert_assets(records, config()).graph
        second = convert_assets(list(reversed(copy.deepcopy(records))), config()).graph
        self.assertTrue(isomorphic(first, second))
        dataset = dataset_node(first, "a/b : ü")
        self.assertEqual(str(dataset), ROOT + "/dataset/a%2Fb%20%3A%20%C3%BC")
        self.assertEqual(len(set(first.subjects(RDF.type, DCAT.Dataset))), 2)

    def test_unknown_contexts_are_blocked_without_any_remote_lookup(self):
        cases = []
        record = asset()
        record["@context"] = "https://untrusted.example/context.jsonld"
        cases.append((record, config()))
        settings = config()
        settings["approvedProperties"].append(str(EX.subject))
        record = asset(
            **{
                str(EX.subject): {
                    "@context": "https://untrusted.example/context.jsonld",
                    "@id": "https://example.org/thing",
                }
            }
        )
        cases.append((record, settings))
        settings = config()
        settings["context"] = {
            "thing": {"@id": str(EX.subject), "@context": "https://untrusted.example/scoped.jsonld"}
        }
        cases.append((asset(), settings))
        for record, settings in cases:
            with (
                self.subTest(record=record, settings=settings),
                patch(
                    "rdflib.plugins.shared.jsonld.context.source_to_json",
                    side_effect=AssertionError("Remote loading must not occur"),
                ) as loader,
            ):
                with self.assertRaises(MappingError):
                    convert_assets([record], settings)
                loader.assert_not_called()

    def test_pinned_context_is_resolved_locally(self):
        settings = config()
        settings["contexts"] = {
            "https://provider.example/context.jsonld": {
                "@context": {
                    "@vocab": EDC,
                    "assetType": {"@id": str(CX.describesAssetType), "@type": "@id"},
                }
            }
        }
        settings["approvedProperties"].append(str(CX.describesAssetType))
        record = asset(assetType="https://example.org/products/Asphalt")
        record["@context"] = "https://provider.example/context.jsonld"
        with patch(
            "rdflib.plugins.shared.jsonld.context.source_to_json",
            side_effect=AssertionError("Remote loading must not occur"),
        ) as loader:
            graph = convert_assets([record], settings).graph
            loader.assert_not_called()
        self.assertIn(
            (
                dataset_node(graph),
                CX.describesAssetType,
                URIRef("https://example.org/products/Asphalt"),
            ),
            graph,
        )

    def test_fallback_fields_cannot_trigger_remote_context_lookup(self):
        settings = config()
        settings["approvedProperties"] = [str(DCTERMS.title)]
        record = asset(
            name={"@context": "https://untrusted.example/context.jsonld", "@value": "Title"}
        )
        with patch(
            "rdflib.plugins.shared.jsonld.context.source_to_json",
            side_effect=AssertionError("Remote loading must not occur"),
        ) as loader:
            try:
                convert_assets([record], settings)
            except MappingError:
                pass
            loader.assert_not_called()

    def test_shacl_rejects_dataset_without_title(self):
        record = {"@id": "untitled", "properties": {"contenttype": "application/json"}}
        graph = convert_assets([record], config()).graph
        result = validate_graph(graph, ROOT)
        self.assertFalse(result["conforms"])
        self.assertTrue(any(error.get("path") == str(DCTERMS.title) for error in result["errors"]))

    def test_topology_rejects_disconnected_core_resources(self):
        for kind in (DCAT.Catalog, DCAT.Dataset, DCAT.Distribution, DCAT.DataService):
            with self.subTest(kind=kind):
                graph = convert_assets([asset()], config()).graph
                graph.add((URIRef("https://example.org/orphan"), RDF.type, kind))
                result = validate_graph(graph, ROOT)
                self.assertFalse(result["conforms"])
                self.assertTrue(
                    any("disconnected" in error["message"] for error in result["errors"])
                )

    def test_topology_rejects_core_resources_without_explicit_type(self):
        graph = convert_assets([asset()], config()).graph
        graph.remove((dataset_node(graph), RDF.type, DCAT.Dataset))
        result = validate_graph(graph, ROOT)
        self.assertFalse(result["conforms"])
        self.assertTrue(any("Explicit" in error["message"] for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
