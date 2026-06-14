"""Practice round persistence + submit endpoint."""

from __future__ import annotations

from app.courses.repository import CourseRepository
from app.courses.router import _stream_turn
from app.db import session_scope


def _make_course_with_module(session) -> str:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Functions")
    course.catalog_id = "cb-c01"
    repo.save(course)
    repo.replace_modules(
        course.id,
        [
            {
                "module_id": "cb-c01-m01",
                "title": "Functions",
                "sequence": 1,
                "estimated_minutes": 60,
                "complete_before": "2026-07-01",
                "scheduled": [],
            }
        ],
    )
    return course.id


def test_practice_round_is_persisted_to_practice_active(session) -> None:
    course_id = _make_course_with_module(session)
    # Drain the SSE generator for a practise turn.
    list(_stream_turn(course_id, "quiz me on this module"))

    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None
        active = course.practice_active
        assert active["module_id"] == "cb-c01-m01"
        assert len(active["questions"]) == 5
        # The answer key is persisted server-side for grading.
        assert all("correct" in q for q in active["questions"])


def _seed_active_round(session, course_id: str, correct_n: int) -> dict:
    """Put a known 5-MCQ round on practice_active and return selections with N correct."""
    repo = CourseRepository(session)
    course = repo.get(course_id)
    assert course is not None
    questions = [
        {"id": f"p{i}", "prompt": f"Q{i}", "choices": ["w", "x", "y", "z"], "correct": "w", "explanation": "e"}
        for i in range(1, 6)
    ]
    course.practice_active = {"module_id": "cb-c01-m01", "title": "Functions", "questions": questions}
    repo.save(course)
    return {f"p{i}": (["w"] if i <= correct_n else ["x"]) for i in range(1, 6)}


def test_submit_ready_streams_take_evaluation_action(client, session) -> None:
    course_id = _make_course_with_module(session)
    selections = _seed_active_round(session, course_id, correct_n=5)

    with client.stream(
        "POST", f"/api/courses/{course_id}/practice/submit", json={"selections": selections}
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert '"type": "action"' in body
    assert "take_evaluation" in body

    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course is not None and not course.practice_active  # cleared after grading


def test_submit_study_streams_go_to_module_action(client, session) -> None:
    course_id = _make_course_with_module(session)
    selections = _seed_active_round(session, course_id, correct_n=0)

    with client.stream(
        "POST", f"/api/courses/{course_id}/practice/submit", json={"selections": selections}
    ) as resp:
        body = "".join(resp.iter_text())
    assert "go_to_module" in body
    assert "take_evaluation" not in body


def test_submit_without_active_round_returns_409(client, session) -> None:
    course_id = _make_course_with_module(session)
    resp = client.post(f"/api/courses/{course_id}/practice/submit", json={"selections": {}})
    assert resp.status_code == 409


def test_submit_missing_course_returns_404(client) -> None:
    resp = client.post("/api/courses/nonexistent-id/practice/submit", json={"selections": {}})
    assert resp.status_code == 404


def test_practise_then_submit_full_loop(client, session) -> None:
    course_id = _make_course_with_module(session)

    # 1) Chat: ask to practise → a practice event is streamed and persisted.
    with client.stream(
        "POST", f"/api/courses/{course_id}/messages", json={"content": "quiz me on this module"}
    ) as resp:
        chat_body = "".join(resp.iter_text())
    assert '"type": "practice"' in chat_body
    assert '"correct":' not in chat_body  # answer-key field never crosses the wire

    with session_scope() as s:
        active = CourseRepository(s).get(course_id).practice_active
    selections = {q["id"]: [q["correct"]] for q in active["questions"]}  # all correct

    # 2) Submit → ready verdict + take_evaluation CTA, round cleared.
    with client.stream(
        "POST", f"/api/courses/{course_id}/practice/submit", json={"selections": selections}
    ) as resp:
        submit_body = "".join(resp.iter_text())
    assert "take_evaluation" in submit_body
    with session_scope() as s:
        assert not CourseRepository(s).get(course_id).practice_active
