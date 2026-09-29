import httpx

from core.shared.fuseki import FusekiClient, FusekiSettings


def test_fuseki_client_replaces_named_graph_and_runs_query() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "head": {"vars": ["dataset"]},
                    "results": {
                        "bindings": [
                            {
                                "dataset": {
                                    "type": "uri",
                                    "value": "https://example.org/datasets/test",
                                }
                            }
                        ]
                    },
                },
            )
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = FusekiClient(
        FusekiSettings(dataset_url="http://fuseki.test/solid"),
        http_client=http_client,
    )

    client.replace_named_graph("urn:catalog:test", "@prefix dcat: <http://www.w3.org/ns/dcat#> .")
    rows = client.query("SELECT ?dataset WHERE { ?dataset ?p ?o }")

    assert [request.method for request in calls] == ["DELETE", "POST", "POST"]
    assert calls[0].url.path == "/solid/data"
    assert calls[1].url.path == "/solid/data"
    assert calls[2].url.path == "/solid/query"
    assert rows == [{"dataset": "https://example.org/datasets/test"}]
