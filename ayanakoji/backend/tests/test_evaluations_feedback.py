"""Tests for the Evaluations tab endpoint, retake (force), and in-chat feedback.

All run in the offline LLM lane (no Azure calls). The feedback path is the fix for
the 'Get Feedback' button: it must produce grounded feedback in the chat instead of
the topic-gate refusal a bare natural-language question used to trigger.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from tests.test_assessment_session import _make_course_with_plan, _seed_banks


def _add_second_module(course_id: str) -> str:
    """Append a second module row so lock progression can be exercised."""
    from app.courses.models import CourseModule
    from app.db import session_scope

    module_id = "cb-c01-m02"
    with session_scope() as s:
        s.add(
            CourseModule(
                course_id=course_id,
                module_id=module_id,
                title="CB Module 2",
                sequence=2,
                estimated_minutes=60,
                complete_before="2026-12-31",
            )
        )
        s.commit()
    return module_id


def _pass_choices(client: TestClient, course_id: str, module_id: str) -> None:
    a = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    for q in a["choice_questions"]:
        client.post(
            f"/api/courses/{course_id}/assessments/{a['id']}/choices/{q['id']}/select",
            json={"selections": ["A"]},
        )
    client.post(f"/api/courses/{course_id}/assessments/{a['id']}/choices/submit")


def _sse_events(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in text.split("\n\n"):
        line = chunk.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


# ── Evaluations list ────────────────────────────────────────────────────────────


def test_evaluations_two_per_module_with_lock_progression(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _add_second_module(course_id)

    evals = client.get(f"/api/courses/{course_id}/evaluations").json()
    # Two evaluations per module, in module order, choices before llm.
    assert len(evals) == 4
    assert [e["type"] for e in evals] == ["choices", "llm", "choices", "llm"]
    assert [e["module_id"] for e in evals] == [
        "cb-c01-m01",
        "cb-c01-m01",
        "cb-c01-m02",
        "cb-c01-m02",
    ]

    by = {(e["module_id"], e["type"]): e for e in evals}
    # Module 1 quiz is open; its oral waits on the quiz; module 2 is fully locked.
    assert by[("cb-c01-m01", "choices")]["locked"] is False
    assert by[("cb-c01-m01", "llm")]["locked"] is True
    assert by[("cb-c01-m02", "choices")]["locked"] is True
    assert by[("cb-c01-m02", "llm")]["locked"] is True


def test_evaluations_oral_unlocks_after_quiz_pass(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    _pass_choices(client, course_id, module_id)
    evals = client.get(f"/api/courses/{course_id}/evaluations").json()
    by = {(e["module_id"], e["type"]): e for e in evals}
    quiz = by[("cb-c01-m01", "choices")]
    oral = by[("cb-c01-m01", "llm")]
    # The quiz now reads as completed (passed) with a review id; the oral is unlocked.
    assert quiz["completed"] is True
    assert quiz["passed"] is True
    assert quiz["score"] == 10.0
    assert quiz["review_assessment_id"]
    assert oral["locked"] is False


# ── Retake ──────────────────────────────────────────────────────────────────────


def test_retake_with_force_allowed_after_pass(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    _pass_choices(client, course_id, module_id)

    # Without force the passed assessment is blocked (existing behaviour).
    blocked = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    )
    assert blocked.status_code == 409

    # With force a fresh attempt is created and persisted.
    retake = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices", "force": "true"},
    )
    assert retake.status_code == 201, retake.text
    body = retake.json()
    assert body["attempt_number"] == 2
    assert len(body["choice_questions"]) == 5
    assert body["passed"] is None


# ── In-chat feedback (the 'Get Feedback' fix) ─────────────────────────────────────


def test_feedback_streams_grounded_text_not_a_refusal(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)

    # Fail the quiz (submit with nothing selected → all wrong).
    a = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    client.post(f"/api/courses/{course_id}/assessments/{a['id']}/choices/submit")

    resp = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/feedback",
        params={"type": "choices"},
    )
    assert resp.status_code == 200, resp.text
    events = _sse_events(resp.text)
    kinds = {e["type"] for e in events}
    assert "phase" in kinds and "token" in kinds and "done" in kinds
    text = "".join(e["token"] for e in events if e["type"] == "token")
    # Grounded feedback, not the topic-gate refusal.
    assert "outside Athenaeum's approved course material" not in text
    assert module_id in text  # cites the module it grounded on
    assert "feedback" in text.lower()


def test_feedback_persists_both_turns_in_chat(
    client: TestClient, assessments_session: Any
) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    a = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/assessments/start",
        params={"type": "choices"},
    ).json()
    client.post(f"/api/courses/{course_id}/assessments/{a['id']}/choices/submit")

    client.post(
        f"/api/courses/{course_id}/modules/{module_id}/feedback",
        params={"type": "choices"},
    )
    messages = client.get(f"/api/courses/{course_id}").json()["messages"]
    roles = [m["role"] for m in messages[-2:]]
    assert roles == ["user", "assistant"]
    assert "feedback" in messages[-2]["content"].lower()
    assert messages[-1]["content"]  # assistant feedback persisted


def test_feedback_rejects_bad_type(client: TestClient, assessments_session: Any) -> None:
    _seed_banks(assessments_session)
    course_id, module_id = _make_course_with_plan(client)
    resp = client.post(
        f"/api/courses/{course_id}/modules/{module_id}/feedback",
        params={"type": "essay"},
    )
    assert resp.status_code == 422
