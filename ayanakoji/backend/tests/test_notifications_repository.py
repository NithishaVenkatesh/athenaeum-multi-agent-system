"""Tests for NotificationRepository: dedup-safe upserts, read/toast state, ledger."""

from __future__ import annotations

from app.notifications.models import (
    KIND_DEADLINE_SOON,
    KIND_NEXT_MODULE,
    SCORE_MISSED,
    _now,
)
from app.notifications.repository import NotificationRepository, make_dedup_key
from sqlmodel import Session


def _repo(session: Session) -> NotificationRepository:
    return NotificationRepository(session)


def test_get_or_create_streak_is_stable(session: Session) -> None:
    repo = _repo(session)
    first = repo.get_or_create_streak("EMP1")
    again = repo.get_or_create_streak("EMP1")
    assert first.persona_id == again.persona_id == "EMP1"
    assert again.points == 0


def test_save_streak_persists_and_bumps_updated_at(session: Session) -> None:
    repo = _repo(session)
    streak = repo.get_or_create_streak("EMP1")
    streak.points = 10
    streak.on_time_streak = 1
    saved = repo.save_streak(streak)
    assert saved.points == 10
    assert repo.get_or_create_streak("EMP1").on_time_streak == 1


def test_upsert_notification_dedups(session: Session) -> None:
    repo = _repo(session)
    args: dict[str, str] = {
        "persona_id": "EMP1",
        "course_id": "c1",
        "module_id": "m1",
        "kind": KIND_NEXT_MODULE,
        "title": "Module done",
        "body": "Start the next one.",
        "link": "/chat/c1/modules/m2",
    }
    first = repo.upsert_notification(**args)
    second = repo.upsert_notification(**args)
    assert first is not None
    assert second is None  # same dedup key → no duplicate
    assert len(repo.list_notifications("EMP1")) == 1


def test_unread_count_and_mark_read(session: Session) -> None:
    repo = _repo(session)
    n = repo.upsert_notification(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=KIND_NEXT_MODULE,
        title="t",
        body="b",
        link="/x",
    )
    assert n is not None
    assert repo.unread_count("EMP1") == 1
    repo.mark_read(n)
    assert repo.unread_count("EMP1") == 0


def test_mark_all_read(session: Session) -> None:
    repo = _repo(session)
    for kind in (KIND_NEXT_MODULE, KIND_DEADLINE_SOON):
        repo.upsert_notification(
            persona_id="EMP1",
            course_id="c1",
            module_id="m1",
            kind=kind,
            title="t",
            body="b",
            link="/x",
        )
    assert repo.unread_count("EMP1") == 2
    changed = repo.mark_all_read("EMP1")
    assert changed == 2
    assert repo.unread_count("EMP1") == 0


def test_mark_toasted(session: Session) -> None:
    repo = _repo(session)
    n = repo.upsert_notification(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=KIND_NEXT_MODULE,
        title="t",
        body="b",
        link="/x",
    )
    assert n is not None
    assert n.toasted is False
    assert repo.mark_toasted([n.id]) == 1
    assert repo.get_notification(n.id) is not None
    assert repo.get_notification(n.id).toasted is True  # type: ignore[union-attr]


def test_notifications_isolated_per_persona(session: Session) -> None:
    repo = _repo(session)
    repo.upsert_notification(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=KIND_NEXT_MODULE,
        title="t",
        body="b",
        link="/x",
    )
    assert len(repo.list_notifications("EMP1")) == 1
    assert len(repo.list_notifications("EMP2")) == 0


def test_scoring_ledger_dedups(session: Session) -> None:
    repo = _repo(session)
    assert repo.has_scoring_event("c1", "m1", SCORE_MISSED) is False
    first = repo.add_scoring_event(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=SCORE_MISSED,
        delta=-2,
        occurred_at=_now(),
    )
    second = repo.add_scoring_event(
        persona_id="EMP1",
        course_id="c1",
        module_id="m1",
        kind=SCORE_MISSED,
        delta=-2,
        occurred_at=_now(),
    )
    assert first is not None
    assert second is None  # ledger dedups on (course, module, kind)
    assert repo.has_scoring_event("c1", "m1", SCORE_MISSED) is True


def test_make_dedup_key_handles_missing_module() -> None:
    assert make_dedup_key("c1", None, "course_complete") == "c1:-:course_complete"
    assert make_dedup_key("c1", "m1", "next_module") == "c1:m1:next_module"
