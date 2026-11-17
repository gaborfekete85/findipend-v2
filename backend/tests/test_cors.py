import importlib

import pytest
from fastapi.testclient import TestClient

import app.main

PREFLIGHT = {
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "authorization",
}


@pytest.fixture
def client_with_origins(monkeypatch):
    """A test client on an app built with CORS_ALLOWED_ORIGINS set (or unset with None)."""

    def build(origins: str | None) -> TestClient:
        if origins is None:
            monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
        return TestClient(importlib.reload(app.main).app)

    yield build
    monkeypatch.undo()
    importlib.reload(app.main)


def preflight(client: TestClient, origin: str):
    return client.options("/api/v1/summary", headers={"Origin": origin, **PREFLIGHT})


def test_preflight_from_localhost_3000_is_allowed_by_default(client_with_origins):
    response = preflight(client_with_origins(None), "http://localhost:3000")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "GET" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:3001", "null"])
def test_preflight_from_other_origin_gets_no_allow_origin(client_with_origins, origin):
    response = preflight(client_with_origins(None), origin)

    assert "access-control-allow-origin" not in response.headers


def test_allowed_origins_come_from_cors_allowed_origins(client_with_origins):
    client = client_with_origins("http://a.test, http://b.test")

    for origin in ("http://a.test", "http://b.test"):
        response = preflight(client, origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-origin" not in preflight(client, "http://localhost:3000").headers


def test_simple_request_from_allowed_origin_gets_allow_origin(client_with_origins):
    response = client_with_origins(None).get(
        "/api/v1/health", headers={"Origin": "http://localhost:3000"}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
