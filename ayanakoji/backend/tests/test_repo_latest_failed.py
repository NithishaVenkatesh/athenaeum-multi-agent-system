"""Repository query that resolves a learner's most recent FAILED test in a course.

Backs the in-chat 'feedback on my failed test': a bare ask resolves to the latest
miss in this course; a module-named ask resolves to that module's latest miss.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.courses.models import Assessment
from app.courses.repository import CourseRepository
from sqlmodel import Session


def _failed(session: Session, course_id: str, module_id: str, type: str, when: datetime) -> None:
    session.add(
        Assessment(
            course_id=course_id,
            module_id=module_id,
            type=type,
            score=2.0,
            passed=False,
            completed_at=when,
        )
    )
    session.commit()


def _passed(session: Session, course_id: str, module_id: str, type: str, when: datetime) -> None:
    session.add(
        Assessment(
            course_id=course_id,
            module_id=module_id,
            type=type,
            score=9.0,
            passed=True,
            completed_at=when,
            passed_at=when,
            attempts_to_pass=1,
        )
    )
    session.commit()


def test_latest_failed_returns_most_recent_miss_across_modules(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")

    _failed(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))
    _failed(session, course.id, "cb-c01-m02", "llm", datetime(2026, 6, 10, tzinfo=UTC))

    latest = repo.latest_failed_assessment(course.id)
    assert latest is not None
    assert (latest.module_id, latest.type) == ("cb-c01-m02", "llm")  # most recent


def test_latest_failed_ignores_passed_and_in_progress(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")

    _passed(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 12, tzinfo=UTC))
    # An in-progress attempt (no completed_at / passed is None) must be ignored.
    session.add(Assessment(course_id=course.id, module_id="cb-c01-m02", type="choices"))
    session.commit()

    assert repo.latest_failed_assessment(course.id) is None


def test_latest_failed_scoped_to_named_module(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")

    _failed(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))
    _failed(session, course.id, "cb-c01-m02", "choices", datetime(2026, 6, 10, tzinfo=UTC))

    scoped = repo.latest_failed_assessment(course.id, module_id="cb-c01-m01")
    assert scoped is not None
    assert scoped.module_id == "cb-c01-m01"


def test_latest_failed_is_course_scoped(session: Session) -> None:
    repo = CourseRepository(session)
    mine = repo.create(persona_id="EMP-001", chat_name="Mine")
    other = repo.create(persona_id="EMP-002", chat_name="Other")

    _failed(session, other.id, "cb-c01-m01", "choices", datetime(2026, 6, 10, tzinfo=UTC))

    assert repo.latest_failed_assessment(mine.id) is None


def test_course_feedback_active_defaults_empty() -> None:
    from app.courses.models import Course

    assert Course(persona_id="EMP-001", chat_name="x").feedback_active == {}
