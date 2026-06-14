"""Tests for the notifications HTTP surface (lazy tick + read/toasted mutations)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.courses.models import Course, CourseModule
from fastapi.testclient import TestClient
from sqlmodel import Session

PERSONA = "EMP1"


def _seed_completed_then_pending(session: Session) -> Course:
    """A course whose first module is done on time, with a second still pending."""
    course = Course(persona_id=PERSONA, chat_name="Cloud Basics")
    session.add(course)
    session.commit()
    session.refresh(course)
    session.add(
        CourseModule(
            course_id=course.id,
            module_id="m1",
            title="Intro",
            sequence=1,
            estimated_minutes=60,
            complete_before="2026-12-20",
            completed=True,
            completed_at=datetime(2026, 6, 12, tzinfo=UTC),
        )
    )
    session.add(
        CourseModule(
            course_id=course.id,
            module_id="m2",
            title="Networking",
            sequence=2,
            estimated_minutes=60,
            complete_before="2026-12-27",
        )
    )
    session.commit()
    return course


def test_get_notifications_empty(client: TestClient) -> None:
    res = client.get("/api/notifications", params={"persona_id": PERSONA})
    assert res.status_code == 200
    body = res.json()
    assert body["notifications"] == []
    assert body["unread_count"] == 0
    assert body["streak"] == {
        "persona_id": PERSONA,
        "points": 0,
        "on_time_streak": 0,
        "miss_streak": 0,
    }


def test_get_notifications_requires_persona(client: TestClient) -> None:
    assert client.get("/api/notifications").status_code == 422


def test_get_runs_lazy_tick_and_returns_feed(client: TestClient, session: Session) -> None:
    course = _seed_completed_then_pending(session)

    body = client.get("/api/notifications", params={"persona_id": PERSONA}).json()

    assert body["unread_count"] == 1
    assert body["streak"]["points"] == 10
    assert len(body["notifications"]) == 1
    note = body["notifications"][0]
    assert note["kind"] == "next_module"
    assert note["link"] == f"/chat/{course.id}/modules/m2"
    assert note["read"] is False


def test_get_is_idempotent(client: TestClient, session: Session) -> None:
    _seed_completed_then_pending(session)
    client.get("/api/notifications", params={"persona_id": PERSONA})
    body = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    assert len(body["notifications"]) == 1  # not re-created
    assert body["streak"]["points"] == 10  # not re-awarded


def test_mark_read_clears_badge(client: TestClient, session: Session) -> None:
    _seed_completed_then_pending(session)
    body = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    nid = body["notifications"][0]["id"]

    read = client.post(f"/api/notifications/{nid}/read")
    assert read.status_code == 200
    assert read.json()["read"] is True

    after = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    assert after["unread_count"] == 0


def test_mark_read_404_for_unknown(client: TestClient) -> None:
    assert client.post("/api/notifications/does-not-exist/read").status_code == 404


def test_mark_all_read(client: TestClient, session: Session) -> None:
    _seed_completed_then_pending(session)
    client.get("/api/notifications", params={"persona_id": PERSONA})
    res = client.post("/api/notifications/read-all", params={"persona_id": PERSONA})
    assert res.status_code == 200
    assert res.json()["changed"] == 1
    body = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    assert body["unread_count"] == 0


def test_mark_toasted(client: TestClient, session: Session) -> None:
    _seed_completed_then_pending(session)
    body = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    nid = body["notifications"][0]["id"]
    assert body["notifications"][0]["toasted"] is False

    res = client.post("/api/notifications/toasted", json={"ids": [nid]})
    assert res.status_code == 200
    assert res.json()["changed"] == 1

    after = client.get("/api/notifications", params={"persona_id": PERSONA}).json()
    assert after["notifications"][0]["toasted"] is True
