"""Tests for system endpoints (health + ping) and the connectivity contract."""

from __future__ import annotations

from app import __version__
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ayanakoji-backend"
    assert body["version"] == __version__


def test_ping_returns_pong_with_contract(client: TestClient) -> None:
    response = client.get("/api/ping")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "pong"
    assert body["service"] == "ayanakoji-backend"
    assert body["version"] == __version__
    # timestamp must be a parseable ISO-8601 string
    assert "T" in body["timestamp"]


def test_ping_timestamp_is_iso8601(client: TestClient) -> None:
    from datetime import datetime

    body = client.get("/api/ping").json()
    # Should not raise.
    parsed = datetime.fromisoformat(body["timestamp"])
    assert parsed.tzinfo is not None


def test_cors_headers_present_for_allowed_origin(client: TestClient) -> None:
    response = client.get("/api/ping", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
