"""Schema tests for the notifications/streak tables.

Verifies init_db creates the three learner-workspace tables and that each model
round-trips with its documented defaults.
"""

from __future__ import annotations

from app.notifications.models import (
    KIND_NEXT_MODULE,
    SCORE_ON_TIME,
    Notification,
    Streak,
    StreakEvent,
    _now,
)
from sqlalchemy import inspect
from sqlmodel import Session


def test_init_db_creates_notification_tables(session: Session) -> None:
    names = set(inspect(session.get_bind()).get_table_names())
    assert {"notification", "streak", "streakevent"} <= names


def test_notification_defaults_round_trip(session: Session) -> None:
    n = Notification(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=KIND_NEXT_MODULE,
        title="Module done",
        body="Start the next one.",
        link="/chat/c1/modules/m2",
        dedup_key="c1:m1:next_module",
    )
    session.add(n)
    session.commit()
    session.refresh(n)
    assert n.id  # uuid assigned
    assert n.read is False
    assert n.toasted is False
    assert n.created_at is not None


def test_streak_defaults(session: Session) -> None:
    s = Streak(persona_id="EMP1")
    session.add(s)
    session.commit()
    session.refresh(s)
    assert s.points == 0
    assert s.on_time_streak == 0
    assert s.miss_streak == 0


def test_streak_event_round_trip(session: Session) -> None:
    e = StreakEvent(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=SCORE_ON_TIME,
        delta=10,
        dedup_key="c1:m1:on_time",
        occurred_at=_now(),
    )
    session.add(e)
    session.commit()
    session.refresh(e)
    assert e.id
    assert e.delta == 10
