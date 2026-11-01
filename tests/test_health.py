"""Smoke tests for the API surface."""

from fastapi.testclient import TestClient

from insmart_api.app import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
