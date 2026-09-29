# Adapted from tmdt-buw/semantic-data-catalog (F. Hoelken et al.), Apache-2.0.
"""Solid registry membership check."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx
from rdflib import Graph, URIRef

from core.interfaces.registry import RegistryCheck
from core.shared.rdf import guess_rdflib_format
from modes.solid.registry_contract import SolidRegistryContract, load_registry_contract

DEFAULT_SOLID_REGISTRY_URL = (
    "https://solid-community-server.tmdt.info/semanticdatacatalog/public/test/"
)

logger = logging.getLogger(__name__)


class SolidRegistryError(RuntimeError):
    pass


def normalize_container_url(value: str) -> str:
    if not value:
        return ""
    return value if value.endswith("/") else f"{value}/"


@dataclass
class SolidRegistryCheck(RegistryCheck):
    contract: SolidRegistryContract = field(default_factory=load_registry_contract)
    registry_url: str | None = None
    cache_ttl_seconds: float | None = None
    timeout_seconds: float | None = None
    http_client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.registry_url is None:
            self.registry_url = os.getenv(
                self.contract.registry_url_env,
                DEFAULT_SOLID_REGISTRY_URL,
            )
        if self.cache_ttl_seconds is None:
            self.cache_ttl_seconds = self._cache_ttl_from_env()
        if self.timeout_seconds is None:
            self.timeout_seconds = self.contract.fetch_timeout_seconds

        self.registry_url = normalize_container_url(self.registry_url)
        self._container_predicates = tuple(
            URIRef(predicate) for predicate in self.contract.container_member_resource_predicates
        )
        self._webid_predicates = tuple(
            URIRef(predicate) for predicate in self.contract.member_resource_webid_predicates
        )
        self._members_cache: set[str] | None = None
        self._cache_expires_at = 0.0
        self.last_error: str | None = None

    def _cache_ttl_from_env(self) -> float:
        raw_value = os.getenv(self.contract.cache_ttl_seconds_env)
        if (
            raw_value is None
            and self.contract.cache_ttl_seconds_env != "SOLID_REGISTRY_CACHE_SECONDS"
        ):
            raw_value = os.getenv("SOLID_REGISTRY_CACHE_SECONDS")
        if raw_value is None:
            return self.contract.cache_default_ttl_seconds
        return float(raw_value)

    def is_member(self, participant_id: str) -> bool:
        webid = self._normalize_webid(participant_id)
        if not webid:
            return False
        return webid in self.load_members()

    def _normalize_webid(self, value: object) -> str:
        webid = str(value or "")
        if self.contract.normalize_trim:
            webid = webid.strip()

        if (
            not self.contract.normalize_preserve_fragment
            or self.contract.normalize_lowercase_scheme_host
        ):
            parts = urlsplit(webid)
            scheme = (
                parts.scheme.lower()
                if self.contract.normalize_lowercase_scheme_host
                else parts.scheme
            )
            netloc = (
                parts.netloc.lower()
                if self.contract.normalize_lowercase_scheme_host
                else parts.netloc
            )
            fragment = parts.fragment if self.contract.normalize_preserve_fragment else ""
            webid = urlunsplit((scheme, netloc, parts.path, parts.query, fragment))

        return webid

    def registry_reachable(self) -> bool:
        try:
            self.load_members(force_refresh=True, allow_stale=False)
            return True
        except SolidRegistryError:
            return False

    def load_members(self, *, force_refresh: bool = False, allow_stale: bool = True) -> set[str]:
        now = time.monotonic()
        if not force_refresh and self._members_cache is not None and now < self._cache_expires_at:
            return set(self._members_cache)

        if not self.registry_url:
            self.last_error = "SOLID_REGISTRY_URL is not configured"
            raise SolidRegistryError(self.last_error)

        try:
            members = self._load_members_uncached()
        except Exception as exc:
            self.last_error = f"Failed to load Solid registry {self.registry_url}: {exc}"
            if allow_stale and self._members_cache is not None:
                logger.warning(
                    "Solid registry refresh failed; serving stale cached membership",
                    extra={"registry_url": self.registry_url, "error": str(exc)},
                )
                return set(self._members_cache)
            raise SolidRegistryError(self.last_error) from exc

        self._members_cache = members
        self._cache_expires_at = now + self.cache_ttl_seconds
        self.last_error = None
        return set(members)

    def _client(self) -> httpx.Client:
        return self.http_client or httpx.Client(timeout=self.timeout_seconds)

    def _fetch_graph(self, url: str) -> Graph:
        client = self._client()
        close_client = self.http_client is None
        try:
            response = client.get(
                url,
                headers={
                    "Accept": (
                        "text/turtle, application/ld+json;q=0.9, "
                        "application/rdf+xml;q=0.8, */*;q=0.1"
                    )
                },
            )
        finally:
            if close_client:
                client.close()

        if response.status_code == 404:
            raise SolidRegistryError(f"registry resource not found: {url}")
        response.raise_for_status()

        graph = Graph()
        content_type = response.headers.get("content-type")
        rdf_format = (
            guess_rdflib_format(content_type)
            if self.contract.registry_rdf_format == "auto"
            else self.contract.registry_rdf_format
        )
        graph.parse(
            data=response.text,
            publicID=url,
            format=rdf_format,
        )
        return graph

    def _load_members_uncached(self) -> set[str]:
        container_graph = self._fetch_graph(self.registry_url)
        resource_urls = self._contained_resource_urls(container_graph)
        members: set[str] = set()

        for resource_url in sorted(resource_urls):
            try:
                member_graph = self._fetch_graph(resource_url)
            except Exception as exc:
                logger.debug(
                    "Skipping unreadable Solid registry member resource",
                    extra={"registry_url": self.registry_url, "resource_url": resource_url},
                    exc_info=True,
                )
                if self.contract.failure_fail_closed:
                    raise SolidRegistryError(
                        f"registry member resource could not be loaded: {resource_url}"
                    ) from exc
                continue
            resource_members = self._members_from_resource_graph(member_graph)
            if resource_members:
                members.update(resource_members)
            else:
                logger.warning(
                    "Solid registry member resource did not yield a configured WebID predicate",
                    extra={"registry_url": self.registry_url, "resource_url": resource_url},
                )

        logger.info(
            "Solid registry membership loaded",
            extra={
                "registry_url": self.registry_url,
                "contained_resources": len(resource_urls),
                "members_resolved": len(members),
            },
        )

        return members

    def _contained_resource_urls(self, graph: Graph) -> set[str]:
        subjects = {URIRef(self.registry_url), URIRef(self.registry_url.rstrip("/"))}
        resource_urls = {
            str(resource)
            for subject in subjects
            for predicate in self._container_predicates
            for resource in graph.objects(subject, predicate)
        }
        if resource_urls:
            return resource_urls

        # Some Solid servers serialize the container subject differently. Keep this
        # fallback to diagnose interop without broadening membership extraction.
        return {
            str(resource)
            for predicate in self._container_predicates
            for resource in graph.objects(None, predicate)
        }

    def _members_from_resource_graph(self, graph: Graph) -> set[str]:
        return {
            self._normalize_webid(member)
            for predicate in self._webid_predicates
            for member in graph.objects(None, predicate)
            if isinstance(member, URIRef)
        }
