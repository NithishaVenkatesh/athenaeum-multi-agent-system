"""Manager Insights HTTP surface: access control + Source 2 (real activity)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.courses.models import Assessment, Course
from fastapi.testclient import TestClient
from sqlmodel import Session

MANAGER_ID = "EMP-011"
LEARNER_ID = "EMP-001"
TEAM_ID = "TEAM-A"


def test_insights_returns_aggregate_dashboard_for_a_manager(client: TestClient) -> None:
    resp = client.get(f"/api/manager/{MANAGER_ID}/insights")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == TEAM_ID
    assert body["manager_codename"] == "Polaris"
    assert body["readiness"]["total"] == body["member_count"]
    # Source 2 empty on a fresh DB → honest empty state and an engagement risk flag.
    assert body["engagement"]["has_activity"] is False
    assert any(r["area"] == "engagement" for r in body["risks"])


def test_insights_rejects_a_non_manager_with_403(client: TestClient) -> None:
    resp = client.get(f"/api/manager/{LEARNER_ID}/insights")
    assert resp.status_code == 403


def test_insights_unknown_persona_is_404(client: TestClient) -> None:
    resp = client.get("/api/manager/EMP-999/insights")
    assert resp.status_code == 404


def test_insights_reflects_real_platform_activity(client: TestClient, session: Session) -> None:
    """Source 2: a team member's passed assessment shows up in engagement aggregates."""
    # Seed a course + a passed assessment for a real team member (EMP-001).
    course = Course(persona_id=LEARNER_ID, chat_name="Vega — AZ-204")
    session.add(course)
    session.commit()
    session.refresh(course)
    session.add(
        Assessment(
            course_id=course.id,
            module_id="cb-c01-m01",
            type="choices",
            score=8.0,
            passed=True,
            attempts_to_pass=1,
            passed_at=datetime.now(UTC),
        )
    )
    session.commit()

    body = client.get(f"/api/manager/{MANAGER_ID}/insights").json()
    engagement = body["engagement"]
    assert engagement["has_activity"] is True
    assert engagement["members_active"] >= 1
    assert engagement["assessments_passed"] >= 1
    assert engagement["modules_with_a_pass"] >= 1
