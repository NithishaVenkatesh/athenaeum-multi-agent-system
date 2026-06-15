"""In-chat feedback end to end through POST /messages (offline lane).

Typing 'why did I fail my quiz' produces grounded feedback (not the off-topic
refusal), pins the test so follow-ups stay grounded, and clears the pin the moment
the learner routes elsewhere. The Get Feedback button sets the same pin.
"""

from __future__ import annotations

import json
from typing import Any

from app.courses.repository import CourseRepository
from app.db import session_scope
from fastapi.testclient import TestClient

from tests.test_assessment_session import _make_course_with_plan, _seed_banks


def _sse(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in text.split("\n\n"):
        line = chunk.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


def _fail_quiz(client: TestClient, course_id: str, module_id: str) -> None:
    a = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    client.post(f"/api/courses/{course_id}/assessments/{a['id']}/choices/submit")


def _say(client: TestClient, course_id: str, content: str) -> list[dict[str, Any]]:
    resp = client.post(f"/api/courses/{course_id}/messages", json={"content": content})
    assert resp.status_code == 200, resp.text
    return _sse(resp.text)


def _feedback_active(course_id: str) -> dict[str, Any]:
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        return dict(course.feedback_active or {})


def test_typed_feedback_is_grounded_and_pins_the_test(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _fail_quiz(client, course_id, module_id)

    events = _say(client, course_id, "why did I fail my quiz?")
    assert events[-1]["type"] == "done"
    assert events[-1]["route"] == "feedback"
    text = "".join(e["token"] for e in events if e["type"] == "token")
    assert "outside Athenaeum's approved course material" not in text  # not a refusal
    assert module_id in text  # grounded + cited

    # The test is pinned so follow-ups stay grounded.
    assert _feedback_active(course_id) == {"module_id": module_id, "type": "choices"}


def test_followup_after_feedback_stays_grounded(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _fail_quiz(client, course_id, module_id)
    _say(client, course_id, "why did I fail my quiz?")

    # A generic follow-up that names nothing still routes to feedback (pinned).
    events = _say(client, course_id, "can you explain that again?")
    assert events[-1]["route"] == "feedback"
    text = "".join(e["token"] for e in events if e["type"] == "token")
    assert module_id in text


def test_pin_clears_when_learner_changes_topic(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _fail_quiz(client, course_id, module_id)
    _say(client, course_id, "why did I fail my quiz?")
    assert _feedback_active(course_id)  # pinned

    events = _say(client, course_id, "I'm ready to take the test")
    assert events[-1]["route"] == "take_evaluation"
    assert _feedback_active(course_id) == {}  # pin cleared on topic change


def test_get_feedback_button_also_sets_the_pin(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _fail_quiz(client, course_id, module_id)

    client.post(
        f"/api/courses/{course_id}/modules/{module_id}/feedback", params={"type": "choices"}
    )
    assert _feedback_active(course_id) == {"module_id": module_id, "type": "choices"}
