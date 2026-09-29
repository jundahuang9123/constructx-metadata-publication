import json
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from core.shared.shacl_validate import ShaclValidationGate
from modes.solid.auth import OidcSolidAuth, TrustedHeaderSolidAuth, jwk_thumbprint
from modes.solid.ingest import SolidIngest
from tests.fixtures import FakeRegistry, MemoryCatalogStore, VALID_TURTLE

ISSUER = "https://idp.example"
REGISTERED_WEBID = "https://example.org/profile/card#me"
UNREGISTERED_WEBID = "https://not.example/profile/card#me"


def _private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_jwk(key: rsa.RSAPrivateKey, *, kid: str | None = None) -> dict[str, str]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    if kid:
        jwk["kid"] = kid
    return jwk


def _oidc_client(access_public_jwk: dict[str, str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == f"{ISSUER}/.well-known/openid-configuration":
            return httpx.Response(200, json={"jwks_uri": f"{ISSUER}/jwks"})
        if str(request.url) == f"{ISSUER}/jwks":
            return httpx.Response(200, json={"keys": [access_public_jwk]})
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _signed_request_headers(webid: str) -> dict[str, str]:
    now = int(time.time())
    access_key = _private_key()
    dpop_key = _private_key()
    dpop_public_jwk = _public_jwk(dpop_key)
    access_public_jwk = _public_jwk(access_key, kid="access-key")

    access_token = jwt.encode(
        {
            "iss": ISSUER,
            "iat": now,
            "exp": now + 300,
            "webid": webid,
            "cnf": {"jkt": jwk_thumbprint(dpop_public_jwk)},
        },
        access_key,
        algorithm="RS256",
        headers={"kid": "access-key"},
    )
    dpop_proof = jwt.encode(
        {
            "htu": "http://testserver/catalog",
            "htm": "POST",
            "iat": now,
            "jti": "test-proof",
        },
        dpop_key,
        algorithm="RS256",
        headers={"typ": "dpop+jwt", "jwk": dpop_public_jwk},
    )
    headers = {
        "Authorization": f"DPoP {access_token}",
        "DPoP": dpop_proof,
        "Content-Type": "text/turtle",
    }
    headers["_access_public_jwk"] = json.dumps(access_public_jwk)
    return headers


def _client_for_oidc(headers: dict[str, str], registry: FakeRegistry) -> TestClient:
    access_public_jwk = json.loads(headers.pop("_access_public_jwk"))
    app = FastAPI()
    app.include_router(
        SolidIngest(
            registry=registry,
            validation=ShaclValidationGate(),
            store=MemoryCatalogStore(),
            auth=OidcSolidAuth(
                issuer=ISSUER,
                http_client=_oidc_client(access_public_jwk),
            ),
        ).routes()
    )
    return TestClient(app)


def test_oidc_valid_token_for_registered_webid_is_accepted() -> None:
    headers = _signed_request_headers(REGISTERED_WEBID)
    client = _client_for_oidc(headers, FakeRegistry({REGISTERED_WEBID}))

    response = client.post("/catalog", content=VALID_TURTLE, headers=headers)

    assert response.status_code == 200
    assert response.json()["participant_id"] == REGISTERED_WEBID


def test_oidc_valid_token_for_unregistered_webid_is_rejected() -> None:
    headers = _signed_request_headers(UNREGISTERED_WEBID)
    client = _client_for_oidc(headers, FakeRegistry({REGISTERED_WEBID}))

    response = client.post("/catalog", content=VALID_TURTLE, headers=headers)

    assert response.status_code == 403
    assert response.json()["stage"] == "registry"


def test_oidc_missing_token_is_rejected_at_auth_stage() -> None:
    access_key = _private_key()
    app = FastAPI()
    app.include_router(
        SolidIngest(
            registry=FakeRegistry({REGISTERED_WEBID}),
            validation=ShaclValidationGate(),
            store=MemoryCatalogStore(),
            auth=OidcSolidAuth(
                issuer=ISSUER,
                http_client=_oidc_client(_public_jwk(access_key, kid="access-key")),
            ),
        ).routes()
    )

    response = TestClient(app).post(
        "/catalog",
        content=VALID_TURTLE,
        headers={"Content-Type": "text/turtle"},
    )

    assert response.status_code == 401
    assert response.json()["stage"] == "auth"
    assert response.json()["error"] == "missing_token"


def test_trusted_header_mode_logs_warning(caplog) -> None:
    caplog.set_level("WARNING", logger="modes.solid.auth")

    TrustedHeaderSolidAuth()

    assert "SOLID_AUTH_MODE=trusted-header is enabled" in caplog.text

