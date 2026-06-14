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
