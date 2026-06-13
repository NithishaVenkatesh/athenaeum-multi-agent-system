"""Learner-only persona filter — backs the account chooser (managers excluded)."""

from __future__ import annotations

from app.workiq.repository import get_repository
from fastapi.testclient import TestClient

MANAGER_CODENAME = "Polaris"


def test_repository_learners_only_excludes_managers() -> None:
    repo = get_repository()
    everyone = repo.list_personas()
    learners = repo.list_personas(learners_only=True)

    assert len(everyone) == 11
    assert len(learners) == 10
    assert all(not p.is_manager for p in learners)
    assert MANAGER_CODENAME not in {p.codename for p in learners}


def test_endpoint_learners_only_true_returns_ten(client: TestClient) -> None:
    resp = client.get("/api/workiq/personas", params={"learners_only": "true"})
    assert resp.status_code == 200
    body = resp.json()

    assert len(body) == 10
    assert all(p["is_manager"] is False for p in body)
    assert MANAGER_CODENAME not in {p["codename"] for p in body}


def test_endpoint_default_still_includes_manager(client: TestClient) -> None:
    resp = client.get("/api/workiq/personas")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body) == 11
    assert MANAGER_CODENAME in {p["codename"] for p in body}
