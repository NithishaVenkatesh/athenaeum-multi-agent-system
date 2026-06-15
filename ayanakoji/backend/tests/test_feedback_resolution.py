"""resolve_feedback_target: which test a chat feedback ask resolves to, course-scoped.

A bare ask → the learner's most recent miss in this course; a module-named ask →
that module's miss; another course named → a redirect; nothing failed → none; and
a pinned follow-up keeps grounding on the same test.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.courses.feedback import resolve_feedback_target
from app.courses.models import Assessment
from app.courses.repository import CourseRepository
from sqlmodel import Session

_MODULES = [
    {"module_id": "cb-c01-m01", "title": "Storage Basics"},
    {"module_id": "cb-c01-m02", "title": "Networking Deep Dive"},
]


def _fail(session: Session, course_id: str, module_id: str, type: str, when: datetime) -> None:
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


def test_bare_ask_resolves_to_most_recent_miss(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")
    _fail(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))
    _fail(session, course.id, "cb-c01-m02", "llm", datetime(2026, 6, 9, tzinfo=UTC))

    res = resolve_feedback_target(
        repo,
        course,
        "give me feedback on my failed test",
        modules=_MODULES,
        other_course_titles=[],
        active=None,
    )
    assert res.kind == "answer"
    assert (res.module_id, res.type) == ("cb-c01-m02", "llm")
    assert res.this_course_title == "Cloud & Backend"


def test_named_module_scopes_to_that_module(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")
    _fail(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))
    _fail(session, course.id, "cb-c01-m02", "choices", datetime(2026, 6, 9, tzinfo=UTC))

    res = resolve_feedback_target(
        repo,
        course,
        "why did I get the networking quiz wrong?",
        modules=_MODULES,
        other_course_titles=[],
        active=None,
    )
    assert res.kind == "answer"
    assert res.module_id == "cb-c01-m02"


def test_other_course_named_redirects(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")
    _fail(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))

    res = resolve_feedback_target(
        repo,
        course,
        "feedback on my data engineering exam",
        modules=_MODULES,
        other_course_titles=["Data Engineering"],
        active=None,
    )
    assert res.kind == "redirect"
    assert res.other_course_title == "Data Engineering"


def test_no_failed_test_returns_none(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")

    res = resolve_feedback_target(
        repo,
        course,
        "give me feedback on my quiz",
        modules=_MODULES,
        other_course_titles=[],
        active=None,
    )
    assert res.kind == "none"


def test_pin_reuses_active_test_for_generic_followup(session: Session) -> None:
    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Cloud & Backend")
    _fail(session, course.id, "cb-c01-m01", "choices", datetime(2026, 6, 1, tzinfo=UTC))
    _fail(session, course.id, "cb-c01-m02", "llm", datetime(2026, 6, 9, tzinfo=UTC))

    res = resolve_feedback_target(
        repo,
        course,
        "wait, can you explain that again?",
        modules=_MODULES,
        other_course_titles=[],
        active={"module_id": "cb-c01-m01", "type": "choices"},
    )
    # Stays on the pinned m01, not the more recent m02 miss.
    assert res.kind == "answer"
    assert (res.module_id, res.type) == ("cb-c01-m01", "choices")
