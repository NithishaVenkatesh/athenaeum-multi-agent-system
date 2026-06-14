"""The chat path stages a plan into pending_modules; approval persists it.

Covers the new preview→approve gate (Tasks 5.1 + 5.2): a built plan is staged,
not written to the modules table, until POST /plan/approve promotes it.
"""

from __future__ import annotations

import json

from app.courses.repository import CourseRepository
from app.db import session_scope
from fastapi.testclient import TestClient


def _parse_sse(text: str) -> list[dict]:  # type: ignore[type-arg]
    out = []
    for block in text.split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def _paced_course(client: TestClient) -> str:
    """Create a course, accept cb-c01, mark fresher, set pace — ready to plan."""
    course_id = client.post(
        "/api/courses", json={"persona_id": "EMP-001", "content": "Let us begin"}
    ).json()["id"]
    client.post(f"/api/courses/{course_id}/accept", json={"catalog_id": "cb-c01"})
    client.post(f"/api/courses/{course_id}/skill/fresher")
    client.post(f"/api/courses/{course_id}/pace", json={"pace": "normal"})
    return course_id


def test_plan_turn_stages_pending_modules_without_persisting(client: TestClient) -> None:
    course_id = _paced_course(client)
    resp = client.post(f"/api/courses/{course_id}/messages", json={"content": "build a study plan"})
    events = _parse_sse(resp.text)
    assert any(e["type"] == "plan" for e in events)
    plan = next(e for e in events if e["type"] == "plan")["plan"]
    assert plan["awaiting_approval"] is True
    # Nothing written to the modules table yet, but staged on the course.
    assert client.get(f"/api/courses/{course_id}/modules").json() == []
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert course.pending_modules, "preview should stage pending_modules"


def test_approve_promotes_pending_modules(client: TestClient) -> None:
    course_id = _paced_course(client)
    client.post(f"/api/courses/{course_id}/messages", json={"content": "build a study plan"})
    resp = client.post(f"/api/courses/{course_id}/plan/approve")
    assert resp.status_code == 200
    modules = resp.json()
    assert len(modules) == 4
    assert all(m["complete_before"] for m in modules)
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        assert course.pending_modules == [], "staging cleared after approval"
    assert len(client.get(f"/api/courses/{course_id}/modules").json()) == 4


def test_approve_without_pending_is_409(client: TestClient) -> None:
    course_id = _paced_course(client)
    # No plan built yet → nothing staged.
    assert client.post(f"/api/courses/{course_id}/plan/approve").status_code == 409
