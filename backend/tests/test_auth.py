import io
import json
import time
import urllib.error
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
ISSUER = "https://clerk.findipend.test"


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
    monkeypatch.setenv("CLERK_ISSUER", ISSUER)
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _token(key=KNOWN_KEY, kid="known", drop=(), **overrides) -> str:
    now = int(time.time())
    claims = {"sub": "user_2abc", "iss": ISSUER, "iat": now, "nbf": now - 5, "exp": now + 60}
    claims.update(overrides)
    for name in drop:
        del claims[name]
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


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_token(iss="https://evil.example"), id="other-issuer"),
        pytest.param(_token(iss=ISSUER + "/"), id="issuer-with-trailing-slash"),
        pytest.param(_token(iss=""), id="empty-issuer"),
        pytest.param(_token(drop=("iss",)), id="no-issuer"),
    ],
)
def test_me_rejects_token_from_another_issuer_with_401(token):
    response = _me(token)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_token(azp="http://evil.example"), id="other-party"),
        pytest.param(_token(azp=""), id="empty-party"),
        pytest.param(_token(), id="no-party"),
    ],
)
def test_me_rejects_unauthorized_party_with_401(monkeypatch, token):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "http://localhost:3000")

    response = _me(token)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("parties", "azp"),
    [
        pytest.param("http://localhost:3000", "http://localhost:3000", id="single"),
        pytest.param(
            "http://localhost:3000, https://app.findipend.test",
            "https://app.findipend.test",
            id="second-of-two",
        ),
    ],
)
def test_me_accepts_authorized_party(monkeypatch, parties, azp):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", parties)

    response = _me(_token(sub="user_2abc", azp=azp))

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_2abc"}


def test_me_ignores_azp_when_authorized_parties_unset():
    response = _me(_token(sub="user_2abc", azp="http://anywhere.example"))

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_2abc"}


def test_me_rejects_empty_sub_with_401():
    response = _me(_token(sub=""))

    assert response.status_code == 401


def _failing_urlopen(error):
    def fake_urlopen(url, *args, **kwargs):
        if isinstance(error, bytes):
            return io.BytesIO(error)
        raise error

    return fake_urlopen


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(urllib.error.URLError("connection refused"), id="network-error"),
        pytest.param(TimeoutError("timed out"), id="timeout"),
        pytest.param(b"<html>Bad Gateway</html>", id="not-json"),
        pytest.param(b"{}", id="json-without-keys"),
        pytest.param(b"[]", id="json-list"),
    ],
)
def test_me_returns_503_when_jwks_fetch_fails(monkeypatch, failure):
    monkeypatch.setattr(urllib.request, "urlopen", _failing_urlopen(failure))
    lenient = TestClient(app, raise_server_exceptions=False)

    response = lenient.get("/api/v1/me", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Could not fetch Clerk signing keys; try again later"}


def test_jwks_failure_is_not_cached(monkeypatch, fetched_urls, jwks_url):
    working_urlopen = urllib.request.urlopen
    monkeypatch.setattr(
        urllib.request, "urlopen", _failing_urlopen(urllib.error.URLError("down"))
    )
    lenient = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {_token(sub='user_2abc')}"}

    failed = lenient.get("/api/v1/me", headers=headers)
    monkeypatch.setattr(urllib.request, "urlopen", working_urlopen)
    recovered = lenient.get("/api/v1/me", headers=headers)

    assert (failed.status_code, recovered.status_code) == (503, 200)
    assert recovered.json() == {"user_id": "user_2abc"}
    assert fetched_urls == [jwks_url]
