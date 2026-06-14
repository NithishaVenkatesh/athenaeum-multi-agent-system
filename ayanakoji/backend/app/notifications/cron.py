"""The notifications/streak cron tick — idempotently derives state from progress.

One ``run_tick`` pass walks every learner's courses and, from the modules' own
``completed`` / ``complete_before`` fields, emits notifications and applies the
streak score. It is the single writer and is fully idempotent: notifications and
scoring events dedup on a stable key, so re-running the tick (on the background
schedule and on each read request) never double-counts.

Streak rules (per persona, applied in chronological order so escalation is right):

* a module completed on or before its deadline → ``+10`` and the on-time streak
  grows; the miss streak resets.
* a deadline that passed without completion → the miss streak grows and the
  penalty escalates with it (``-2``, ``-4``, ``-6`` …); the on-time streak resets.

Notifications: ``next_module`` when a module is done and a next one is waiting,
``course_complete`` when the last module is done, ``deadline_soon`` within
``NOTIFY_DEADLINE_SOON_DAYS`` of an unfinished module's deadline, and
``deadline_missed`` once that deadline passes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlmodel import Session, select

from app.agent.clock import today_in_timezone
from app.courses.models import Course, CourseModule
from app.courses.repository import CourseRepository
from app.db import session_scope
from app.notifications.models import (
    KIND_COURSE_COMPLETE,
    KIND_DEADLINE_MISSED,
    KIND_DEADLINE_SOON,
    KIND_NEXT_MODULE,
    POINTS_MISS_STEP,
    POINTS_ON_TIME,
    SCORE_MISSED,
    SCORE_ON_TIME,
)
from app.notifications.repository import NotificationRepository

logger = logging.getLogger(__name__)

# A module's deadline counts as "soon" within this many days (inclusive, and
# including the due date itself). The learner asked us to pick this — two days
# gives a real heads-up without crying wolf every tick.
NOTIFY_DEADLINE_SOON_DAYS = 2


@dataclass(frozen=True)
class _ScoringEvent:
    """A queued scoring event, applied to the streak once all are sorted by time."""

    kind: str  # SCORE_ON_TIME | SCORE_MISSED
    course_id: str
    module_id: str
    occurred_at: datetime


@dataclass
class TickSummary:
    """Observability for one tick pass (returned for logging/tests)."""

    personas: int = 0
    notifications_created: int = 0
    scoring_events_applied: int = 0


def _parse_deadline(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _as_utc(value: datetime) -> datetime:
    """Treat a tz-naive datetime (SQLite drops tzinfo on round-trip) as UTC.

    Scoring events are sorted by ``occurred_at``; mixing naive (``completed_at``
    read back from SQLite) and aware (constructed deadline) datetimes would raise.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _module_link(course_id: str, module_id: str) -> str:
    return f"/chat/{course_id}/modules/{module_id}"


def evaluate_persona(
    notif_repo: NotificationRepository,
    course_repo: CourseRepository,
    persona_id: str,
    today: date,
    *,
    soon_days: int = NOTIFY_DEADLINE_SOON_DAYS,
) -> TickSummary:
    """Derive notifications + scoring for one persona's courses (idempotent)."""
    summary = TickSummary(personas=1)
    scoring: list[_ScoringEvent] = []

    for course in course_repo.list_for_persona(persona_id):
        modules = course_repo.list_modules(course.id)
        by_seq = {m.sequence: m for m in modules}
        all_complete = bool(modules) and all(m.completed for m in modules)
        for module in modules:
            summary.notifications_created += _evaluate_module(
                notif_repo,
                persona_id=persona_id,
                course=course,
                module=module,
                next_module=by_seq.get(module.sequence + 1),
                all_complete=all_complete,
                today=today,
                soon_days=soon_days,
                scoring=scoring,
            )

    summary.scoring_events_applied = _apply_scoring(notif_repo, persona_id, scoring)
    return summary


def _evaluate_module(
    notif_repo: NotificationRepository,
    *,
    persona_id: str,
    course: Course,
    module: CourseModule,
    next_module: CourseModule | None,
    all_complete: bool,
    today: date,
    soon_days: int,
    scoring: list[_ScoringEvent],
) -> int:
    """Emit any notifications for one module and queue its scoring; return #created."""
    deadline = _parse_deadline(module.complete_before)
    if deadline is None:
        return 0

    if module.completed:
        return _evaluate_completed(
            notif_repo,
            persona_id=persona_id,
            course=course,
            module=module,
            next_module=next_module,
            all_complete=all_complete,
            deadline=deadline,
            scoring=scoring,
        )
    return _evaluate_pending(
        notif_repo,
        persona_id=persona_id,
        course=course,
        module=module,
        deadline=deadline,
        today=today,
        soon_days=soon_days,
        scoring=scoring,
    )


def _evaluate_completed(
    notif_repo: NotificationRepository,
    *,
    persona_id: str,
    course: Course,
    module: CourseModule,
    next_module: CourseModule | None,
    all_complete: bool,
    deadline: date,
    scoring: list[_ScoringEvent],
) -> int:
    created = 0
    # Award an on-time completion exactly once (ledger-deduped before queueing).
    completed_at = module.completed_at
    if (
        completed_at is not None
        and completed_at.date() <= deadline
        and not notif_repo.has_scoring_event(course.id, module.module_id, SCORE_ON_TIME)
    ):
        scoring.append(
            _ScoringEvent(SCORE_ON_TIME, course.id, module.module_id, _as_utc(completed_at))
        )

    if next_module is not None and not next_module.completed:
        created += _emit(
            notif_repo,
            persona_id=persona_id,
            course_id=course.id,
            module_id=module.module_id,
            kind=KIND_NEXT_MODULE,
            title="Module complete",
            body=(f"You finished “{module.title}”. Get started with “{next_module.title}” next."),
            link=_module_link(course.id, next_module.module_id),
        )
    elif next_module is None and all_complete:
        # Last module done and every module complete → the course is finished.
        created += _emit(
            notif_repo,
            persona_id=persona_id,
            course_id=course.id,
            module_id=module.module_id,
            kind=KIND_COURSE_COMPLETE,
            title="Course complete",
            body=f"You completed every module in “{course.chat_name}”. Outstanding work.",
            link=f"/chat/{course.id}",
        )
    return created


def _evaluate_pending(
    notif_repo: NotificationRepository,
    *,
    persona_id: str,
    course: Course,
    module: CourseModule,
    deadline: date,
    today: date,
    soon_days: int,
    scoring: list[_ScoringEvent],
) -> int:
    if today > deadline:
        # Missed: penalise once (ledger-deduped) and surface a recoverable nudge.
        if not notif_repo.has_scoring_event(course.id, module.module_id, SCORE_MISSED):
            occurred = datetime(deadline.year, deadline.month, deadline.day, tzinfo=UTC)
            scoring.append(_ScoringEvent(SCORE_MISSED, course.id, module.module_id, occurred))
        return _emit(
            notif_repo,
            persona_id=persona_id,
            course_id=course.id,
            module_id=module.module_id,
            kind=KIND_DEADLINE_MISSED,
            title="Deadline missed",
            body=(
                f"“{module.title}” was due {module.complete_before}. Pick it back up "
                f"to recover your streak."
            ),
            link=_module_link(course.id, module.module_id),
        )
    if (deadline - today).days <= soon_days:
        return _emit(
            notif_repo,
            persona_id=persona_id,
            course_id=course.id,
            module_id=module.module_id,
            kind=KIND_DEADLINE_SOON,
            title="Deadline approaching",
            body=(f"“{module.title}” is due {module.complete_before}. Jump in and finish it fast."),
            link=_module_link(course.id, module.module_id),
        )
    return 0


def _emit(
    notif_repo: NotificationRepository,
    *,
    persona_id: str,
    course_id: str,
    module_id: str,
    kind: str,
    title: str,
    body: str,
    link: str,
) -> int:
    """Upsert a notification; return 1 if it was newly created, else 0."""
    created = notif_repo.upsert_notification(
        persona_id=persona_id,
        course_id=course_id,
        module_id=module_id,
        kind=kind,
        title=title,
        body=body,
        link=link,
    )
    return 1 if created is not None else 0


def _apply_scoring(
    notif_repo: NotificationRepository,
    persona_id: str,
    scoring: list[_ScoringEvent],
) -> int:
    """Apply queued scoring events to the streak in chronological order (race-safe).

    The ledger insert is the gate: the streak counters only move when the event
    actually inserts, so a concurrent tick that already applied an event can't
    cause a double count.
    """
    if not scoring:
        return 0
    streak = notif_repo.get_or_create_streak(persona_id)
    applied = 0
    for event in sorted(scoring, key=lambda e: e.occurred_at):
        if event.kind == SCORE_ON_TIME:
            new_on_time = streak.on_time_streak + 1
            new_miss = 0
            delta = POINTS_ON_TIME
        else:
            new_miss = streak.miss_streak + 1
            new_on_time = 0
            delta = -POINTS_MISS_STEP * new_miss
        recorded = notif_repo.add_scoring_event(
            persona_id=persona_id,
            course_id=event.course_id,
            module_id=event.module_id,
            kind=event.kind,
            delta=delta,
            occurred_at=event.occurred_at,
        )
        if recorded is None:
            continue  # another tick already applied this event — don't double-count
        streak.points += delta
        streak.on_time_streak = new_on_time
        streak.miss_streak = new_miss
        applied += 1
    notif_repo.save_streak(streak)
    return applied


def persona_timezone(persona_id: str) -> str | None:
    """Resolve a persona's IANA timezone for the date anchor (None → UTC fallback)."""
    try:
        from app.workiq.repository import get_repository

        persona = get_repository().get_persona(persona_id)
    except Exception as exc:  # pragma: no cover - defensive: data load shouldn't break the tick
        logger.warning("could not resolve timezone for %s: %s", persona_id, exc)
        return None
    return persona.timezone if persona else None


def _distinct_persona_ids(session: Session) -> list[str]:
    return list(session.exec(select(Course.persona_id).distinct()).all())


def run_tick(*, soon_days: int = NOTIFY_DEADLINE_SOON_DAYS) -> TickSummary:
    """Run one notifications/streak pass across every persona that has courses."""
    total = TickSummary()
    with session_scope() as session:
        notif_repo = NotificationRepository(session)
        course_repo = CourseRepository(session)
        for persona_id in _distinct_persona_ids(session):
            today = today_in_timezone(persona_timezone(persona_id))
            result = evaluate_persona(
                notif_repo, course_repo, persona_id, today, soon_days=soon_days
            )
            total.personas += 1
            total.notifications_created += result.notifications_created
            total.scoring_events_applied += result.scoring_events_applied
    return total
