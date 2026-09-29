import logging
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from modes.solid.registry import SolidRegistryCheck, SolidRegistryError
from modes.solid.registry_contract import SolidRegistryContract, load_registry_contract

REGISTRY_URL = "https://registry.example/public/test/"
WEBID_ONE = "https://pod.example/alice/profile/card#me"
WEBID_TWO = "https://pod.example/bob/profile/card#me"
WEBID_FALLBACK = "https://pod.example/fallback/profile/card#me"
FIXTURE_DIR = Path(__file__).parent / "data" / "solid-registry"


def _client_for(responses: dict[str, str | tuple[int, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.get(str(request.url), (500, "unexpected URL"))
        status, body = response if isinstance(response, tuple) else (200, response)
        return httpx.Response(status, text=body, headers={"Content-Type": "text/turtle"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _registry(
    client: httpx.Client,
    contract: SolidRegistryContract | None = None,
) -> SolidRegistryCheck:
    return SolidRegistryCheck(
        contract=contract or load_registry_contract(),
        registry_url=REGISTRY_URL,
        cache_ttl_seconds=0,
        http_client=client,
    )


def test_registry_reads_two_level_ldp_member_resources() -> None:
    client = _client_for(
        {
            REGISTRY_URL: f"""
                @prefix ldp: <http://www.w3.org/ns/ldp#> .
                <{REGISTRY_URL}> ldp:contains
                    <{REGISTRY_URL}member-alice>,
                    <{REGISTRY_URL}member-bob> .
            """,
            f"{REGISTRY_URL}member-alice": f"""
                @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                <#it> a foaf:Group ;
                    foaf:member <{WEBID_ONE}> .
            """,
            f"{REGISTRY_URL}member-bob": f"""
                @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                <#it> a foaf:Group ;
                    foaf:member <{WEBID_TWO}> .
            """,
        }
    )

    registry = _registry(client)

    assert registry.is_member(WEBID_ONE)
    assert registry.is_member(WEBID_TWO)
    assert not registry.is_member("https://pod.example/not-listed/profile/card#me")


def test_registry_falls_back_to_first_thing_when_it_is_absent() -> None:
    client = _client_for(
        {
            REGISTRY_URL: f"""
                @prefix ldp: <http://www.w3.org/ns/ldp#> .
                <{REGISTRY_URL}> ldp:contains <{REGISTRY_URL}member-fallback> .
            """,
            f"{REGISTRY_URL}member-fallback": f"""
                @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                <{REGISTRY_URL}member-fallback> a foaf:Group ;
                    foaf:member <{WEBID_FALLBACK}> .
            """,
        }
    )

    assert _registry(client).is_member(WEBID_FALLBACK)


def test_registry_warns_on_member_resource_without_webid_predicate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="modes.solid.registry")
    client = _client_for(
        {
            REGISTRY_URL: f"""
                @prefix ldp: <http://www.w3.org/ns/ldp#> .
                <{REGISTRY_URL}> ldp:contains
                    <{REGISTRY_URL}member-empty>,
                    <{REGISTRY_URL}member-alice> .
            """,
            f"{REGISTRY_URL}member-empty": """
                @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                <#it> a foaf:Group .
            """,
            f"{REGISTRY_URL}member-alice": f"""
                @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                <#it> a foaf:Group ;
                    foaf:member <{WEBID_ONE}> .
            """,
        }
    )

    registry = _registry(client)

    assert registry.is_member(WEBID_ONE)
    assert "did not yield a configured WebID predicate" in caplog.text


def test_registry_reads_default_florian_style_fixture_files() -> None:
    client = _client_for(
        {
            REGISTRY_URL: (FIXTURE_DIR / "registry-container.ttl").read_text(encoding="utf-8"),
            f"{REGISTRY_URL}member-alice": (FIXTURE_DIR / "member-resource.ttl").read_text(
                encoding="utf-8"
            ),
        }
    )

    assert _registry(client).is_member(WEBID_ONE)


def test_registry_uses_configured_container_predicate() -> None:
    contract = replace(
        load_registry_contract(),
        container_member_resource_predicates=("https://example.org/vocab#hasParticipantRecord",),
    )
    client = _client_for(
        {
            REGISTRY_URL: (FIXTURE_DIR / "custom-predicate-registry.ttl").read_text(
                encoding="utf-8"
            ),
            f"{REGISTRY_URL}member-alice": (FIXTURE_DIR / "member-resource.ttl").read_text(
                encoding="utf-8"
            ),
        }
    )

    assert _registry(client, contract=contract).is_member(WEBID_ONE)


def test_registry_uses_configured_webid_predicate() -> None:
    contract = replace(
        load_registry_contract(),
        member_resource_webid_predicates=("https://schema.org/member",),
    )
    client = _client_for(
        {
            REGISTRY_URL: (FIXTURE_DIR / "registry-container.ttl").read_text(encoding="utf-8"),
            f"{REGISTRY_URL}member-alice": (
                FIXTURE_DIR / "custom-predicate-member.ttl"
            ).read_text(encoding="utf-8"),
        }
    )

    assert _registry(client, contract=contract).is_member(WEBID_ONE)


def test_registry_404_fails_closed() -> None:
    registry = _registry(_client_for({REGISTRY_URL: (404, "")}))

    with pytest.raises(SolidRegistryError):
        registry.is_member(WEBID_ONE)


def test_registry_refresh_failure_can_serve_existing_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                text=f"""
                    @prefix ldp: <http://www.w3.org/ns/ldp#> .
                    <{REGISTRY_URL}> ldp:contains <{REGISTRY_URL}member-alice> .
                """,
                headers={"Content-Type": "text/turtle"},
            )
        if calls == 2:
            return httpx.Response(
                200,
                text=f"""
                    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
                    <#it> a foaf:Group ;
                        foaf:member <{WEBID_ONE}> .
                """,
                headers={"Content-Type": "text/turtle"},
            )
        return httpx.Response(503, text="down")

    registry = _registry(httpx.Client(transport=httpx.MockTransport(handler)))

    assert registry.is_member(WEBID_ONE)
    assert registry.is_member(WEBID_ONE)
    assert not registry.registry_reachable()
