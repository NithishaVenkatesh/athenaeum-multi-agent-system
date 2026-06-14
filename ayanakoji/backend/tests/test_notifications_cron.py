"""Tests for the notifications/streak cron evaluation.

Drives ``evaluate_persona`` against seeded courses/modules with a fixed ``today``
so the deadline math and streak escalation are deterministic and offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.courses.models import Course, CourseModule
from app.courses.repository import CourseRepository
from app.notifications.cron import evaluate_persona
from app.notifications.models import (
    KIND_COURSE_COMPLETE,
    KIND_DEADLINE_MISSED,
    KIND_DEADLINE_SOON,
    KIND_NEXT_MODULE,
)
from app.notifications.repository import NotificationRepository
from sqlmodel import Session

TODAY = date(2026, 6, 14)
PERSONA = "EMP1"


def _add_course(session: Session, *, chat_name: str = "Cloud Basics") -> Course:
    course = Course(persona_id=PERSONA, chat_name=chat_name)
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


def _add_module(
    session: Session,
    course_id: str,
    *,
    module_id: str,
    sequence: int,
    complete_before: str,
    title: str = "Module",
    completed: bool = False,
    completed_at: datetime | None = None,
) -> CourseModule:
    module = CourseModule(
        course_id=course_id,
        module_id=module_id,
        title=title,
        sequence=sequence,
        estimated_minutes=60,
        complete_before=complete_before,
        completed=completed,
        completed_at=completed_at,
    )
    session.add(module)
    session.commit()
    session.refresh(module)
    return module


def _run(session: Session) -> None:
    evaluate_persona(NotificationRepository(session), CourseRepository(session), PERSONA, TODAY)


def _kinds(session: Session) -> list[str]:
    return [n.kind for n in NotificationRepository(session).list_notifications(PERSONA)]


def test_on_time_completion_awards_points_and_next_module(session: Session) -> None:
    course = _add_course(session)
    _add_module(
        session,
        course.id,
        module_id="m1",
        sequence=1,
        title="Intro",
        complete_before="2026-06-20",
        completed=True,
        completed_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    _add_module(
        session,
        course.id,
        module_id="m2",
        sequence=2,
        title="Networking",
        complete_before="2026-07-10",
    )

    _run(session)

    repo = NotificationRepository(session)
    streak = repo.get_or_create_streak(PERSONA)
    assert streak.points == 10
    assert streak.on_time_streak == 1
    assert streak.miss_streak == 0

    notes = repo.list_notifications(PERSONA)
    assert len(notes) == 1
    assert notes[0].kind == KIND_NEXT_MODULE
    assert notes[0].link == f"/chat/{course.id}/modules/m2"


def test_single_module_completion_marks_course_complete(session: Session) -> None:
    course = _add_course(session)
    _add_module(
        session,
        course.id,
        module_id="m1",
        sequence=1,
        complete_before="2026-06-20",
        completed=True,
        completed_at=datetime(2026, 6, 12, tzinfo=UTC),
    )

    _run(session)

    assert _kinds(session) == [KIND_COURSE_COMPLETE]
    assert NotificationRepository(session).get_or_create_streak(PERSONA).points == 10


def test_deadline_soon_notifies_without_scoring(session: Session) -> None:
    course = _add_course(session)
    _add_module(
        session, course.id, module_id="m1", sequence=1, complete_before="2026-06-15"
    )  # due tomorrow

    _run(session)

    assert _kinds(session) == [KIND_DEADLINE_SOON]
    assert NotificationRepository(session).get_or_create_streak(PERSONA).points == 0


def test_far_deadline_is_silent(session: Session) -> None:
    course = _add_course(session)
    _add_module(session, course.id, module_id="m1", sequence=1, complete_before="2026-07-30")

    _run(session)

    assert _kinds(session) == []


def test_missed_deadline_penalises_and_notifies(session: Session) -> None:
    course = _add_course(session)
    _add_module(
        session, course.id, module_id="m1", sequence=1, complete_before="2026-06-10"
    )  # overdue

    _run(session)

    repo = NotificationRepository(session)
    streak = repo.get_or_create_streak(PERSONA)
    assert streak.points == -2
    assert streak.miss_streak == 1
    assert streak.on_time_streak == 0
    assert _kinds(session) == [KIND_DEADLINE_MISSED]


def test_consecutive_misses_escalate(session: Session) -> None:
    course = _add_course(session)
    _add_module(session, course.id, module_id="m1", sequence=1, complete_before="2026-06-10")
    _add_module(session, course.id, module_id="m2", sequence=2, complete_before="2026-06-12")

    _run(session)

    streak = NotificationRepository(session).get_or_create_streak(PERSONA)
    # -2 (first miss) then -4 (second consecutive miss) = -6
    assert streak.points == -6
    assert streak.miss_streak == 2


def test_on_time_completion_resets_miss_escalation(session: Session) -> None:
    course = _add_course(session)
    # Missed earlier (deadline 06-10), then an on-time completion afterwards (06-12).
    _add_module(session, course.id, module_id="m1", sequence=1, complete_before="2026-06-10")
    _add_module(
        session,
        course.id,
        module_id="m2",
        sequence=2,
        complete_before="2026-06-20",
        completed=True,
        completed_at=datetime(2026, 6, 12, tzinfo=UTC),
    )

    _run(session)

    streak = NotificationRepository(session).get_or_create_streak(PERSONA)
    # chronological: miss 06-10 (-2), then on-time 06-12 (+10) → 8, miss streak reset
    assert streak.points == 8
    assert streak.miss_streak == 0
    assert streak.on_time_streak == 1


def test_tick_is_idempotent(session: Session) -> None:
    course = _add_course(session)
    _add_module(
        session,
        course.id,
        module_id="m1",
        sequence=1,
        complete_before="2026-06-20",
        completed=True,
        completed_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    _add_module(session, course.id, module_id="m2", sequence=2, complete_before="2026-07-10")

    _run(session)
    _run(session)
    _run(session)

    repo = NotificationRepository(session)
    assert repo.get_or_create_streak(PERSONA).points == 10  # awarded once
    assert len(repo.list_notifications(PERSONA)) == 1  # emitted once
