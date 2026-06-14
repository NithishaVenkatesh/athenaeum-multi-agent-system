"""Endpoint tests for the assessment-bank query API."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.assessments.loader import seed_database
from app.assessments.models import AssessmentBank
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.test_assessments_loader import _write_banks
from tests.test_assessments_validation import make_valid_bank


@pytest.fixture
def seeded(assessments_session: Session, tmp_path: Path) -> dict[str, str]:
    """Seed two courses' banks; return {module_id-kind: assessment_id} for lookups."""
    banks = [
        make_valid_bank("cb-c01", "cb-c01-m01"),
        make_valid_bank("cb-c01", "cb-c01-m02"),
        make_valid_bank("cb-c02", "cb-c02-m01"),
    ]
    _write_banks(tmp_path, banks)
    seed_database(assessments_session, root=tmp_path)
    rows = assessments_session.exec(select(AssessmentBank)).all()
    return {f"{r.module_id}-{r.kind}": r.id for r in rows}


def test_get_choices_assessment_returns_questions(
    client: TestClient, seeded: dict[str, str]
) -> None:
    aid = seeded["cb-c01-m01-choices"]
    resp = client.get(f"/api/assessments/{aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "choices"
    assert body["module_id"] == "cb-c01-m01"
    assert len(body["choice_questions"]) == 5
    assert body["llm_questions"] == []
    first = body["choice_questions"][0]
    assert first["id"] == "cb-c01-m01-c01"
    assert first["kind"] in {"mcq", "msq"}
    assert set(first["correct_answers"]).issubset(set(first["choices"]))


def test_get_llm_assessment_returns_reference_answers(
    client: TestClient, seeded: dict[str, str]
) -> None:
    aid = seeded["cb-c01-m01-llm"]
    resp = client.get(f"/api/assessments/{aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "llm"
    assert len(body["llm_questions"]) == 3
    assert body["choice_questions"] == []
    assert body["llm_questions"][0]["reference_answer"]


def test_get_unknown_assessment_is_404(client: TestClient, seeded: dict[str, str]) -> None:
    resp = client.get("/api/assessments/does-not-exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_by_module_returns_both_bank_ids(client: TestClient, seeded: dict[str, str]) -> None:
    resp = client.get("/api/assessments/by-module/cb-c01-m01")
    assert resp.status_code == 200
    body = resp.json()
    assert body["module_id"] == "cb-c01-m01"
    expected = {seeded["cb-c01-m01-choices"], seeded["cb-c01-m01-llm"]}
    assert set(body["assessment_ids"]) == expected
    assert len(body["assessment_ids"]) == 2


def test_by_module_unknown_module_is_empty(client: TestClient, seeded: dict[str, str]) -> None:
    resp = client.get("/api/assessments/by-module/cb-c09-m09")
    assert resp.status_code == 200
    assert resp.json()["assessment_ids"] == []
