import io
import json
import time
import urllib.request
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.main import app

client = TestClient(app)

KNOWN_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
UNKNOWN_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict:
    jwk = RSAAlgorithm.to_jwk(KNOWN_KEY.public_key(), as_dict=True)
    jwk.update(kid="known", use="sig", alg="RS256")
    return {"keys": [jwk]}


@pytest.fixture
def jwks_url() -> str:
    # A fresh URL per test, so a JWKS cached by an earlier test is never reused.
    return f"https://clerk.test/{uuid.uuid4()}/.well-known/jwks.json"


@pytest.fixture(autouse=True)
def fetched_urls(monkeypatch, jwks_url):
    """Stub the network: urlopen serves the test JWKS and records each URL fetched."""
    calls: list[str] = []

    def fake_urlopen(url, *args, **kwargs):
        calls.append(getattr(url, "full_url", url))
        return io.BytesIO(json.dumps(_jwks()).encode())

    monkeypatch.setenv("CLERK_JWKS_URL", jwks_url)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _token(key=KNOWN_KEY, kid="known", **overrides) -> str:
    now = int(time.time())
    claims = {"sub": "user_2abc", "iat": now, "nbf": now - 5, "exp": now + 60}
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def _me(token: str | None):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return client.get("/api/v1/me", headers=headers)


def test_me_returns_sub_claim_for_valid_token():
    response = _me(_token(sub="user_2abc"))

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_2abc"}


def test_me_returns_the_callers_own_sub():
    response = _me(_token(sub="user_other"))

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_other"}


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(None, id="no-authorization-header"),
        pytest.param("not-a-jwt", id="malformed"),
        pytest.param(_token(exp=int(time.time()) - 10), id="expired"),
        pytest.param(_token(key=UNKNOWN_KEY, kid="unknown"), id="unknown-kid"),
        pytest.param(_token(key=UNKNOWN_KEY, kid="known"), id="known-kid-wrong-key"),
        pytest.param(_token(nbf=int(time.time()) + 600), id="not-yet-valid"),
    ],
)
def test_me_rejects_unverified_requests_with_401(token):
    response = _me(token)

    assert response.status_code == 401


def test_me_rejects_non_bearer_scheme_with_401():
    response = client.get("/api/v1/me", headers={"Authorization": f"Basic {_token()}"})

    assert response.status_code == 401


def test_jwks_fetched_once_for_two_valid_requests(fetched_urls, jwks_url):
    first = _me(_token())
    second = _me(_token())

    assert (first.status_code, second.status_code) == (200, 200)
    assert fetched_urls == [jwks_url]
