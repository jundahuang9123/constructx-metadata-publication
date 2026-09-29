"""Regression checks for context boundaries and local/central topology agreement."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rdflib import DCAT, DCTERMS, URIRef

from constructx_catalog_publisher.converter import EDC, MappingError, convert_assets, safe_contexts
from constructx_catalog_publisher.integration import inventory_from_connector
from constructx_catalog_publisher.validation import validate_graph


def inputs():
    config = {
        "sourceId": "a",
        "catalogIri": "https://example.org/catalog/a",
        "title": "A",
        "publisherIri": "did:web:example.org",
        "dspEndpoint": "https://example.org/dsp",
        "selection": {"allAssets": True},
        "approvedProperties": [str(DCTERMS.title), "urn:custom:term"],
    }
    return {"@id": "asset", "properties": {"name": "Asset"}}, config


def test_scoped_context_pin_cycle_fails_as_mapping_error():
    pins = {"urn:ctx:a": {"term": {"@id": "urn:term", "@context": "urn:ctx:a"}}}
    with pytest.raises(MappingError, match="context"):
        safe_contexts("urn:ctx:a", pins)


def test_context_arrays_preserve_prefixes_and_values():
    asset, config = inputs()
    asset["@context"] = [{"@vocab": EDC}, {"custom": "urn:custom:"}]
    asset["properties"]["custom:term"] = {"@id": "urn:concept:wall"}
    result = convert_assets([asset], config)
    assert (None, URIRef("urn:custom:term"), URIRef("urn:concept:wall")) in result.graph
    assert validate_graph(result.graph, config["catalogIri"])["conforms"]


def test_nested_backend_properties_are_rejected_even_in_approved_subtree():
    asset, config = inputs()
    asset["properties"]["urn:custom:term"] = {"edc:dataAddress": {"edc:baseUrl": "PRIVATE"}}
    with pytest.raises(MappingError, match="nested private"):
        convert_assets([asset], config)


def test_relative_metadata_identifiers_do_not_become_local_file_uris():
    asset, config = inputs()
    asset["properties"]["urn:custom:term"] = {"@id": "relative-resource"}
    with pytest.raises(MappingError, match="absolute"):
        convert_assets([asset], config)


def test_local_validation_rejects_structural_links_on_untyped_disconnected_nodes():
    asset, config = inputs()
    graph = convert_assets([asset], config).graph
    graph.add((URIRef("urn:outside"), DCAT.dataset, next(graph.objects(None, DCAT.dataset))))
    assert not validate_graph(graph, config["catalogIri"])["conforms"]


def test_colleague_bridge_uses_existing_client_configuration_only():
    client = SimpleNamespace(
        config=SimpleNamespace(
            management_api="https://connector.example/management", management_key="example-test-key"
        )
    )
    with patch("constructx_catalog_publisher.integration.InventoryClient") as adapter:
        expected = adapter.return_value.harvest.return_value
        assert inventory_from_connector(client, page_size=25) is expected
        adapter.assert_called_once_with(
            "https://connector.example/management", "example-test-key", page_size=25
        )
