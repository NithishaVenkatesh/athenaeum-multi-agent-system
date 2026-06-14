"""Session-scoped data access for notifications and the streak score.

Repository pattern (rules/common/patterns.md): the cron tick and the read API
depend on this typed surface, not on raw SQLModel queries. Writes are dedup-safe
— ``upsert_notification`` and ``add_scoring_event`` no-op on a duplicate
``dedup_key`` (catching the unique-constraint race between the background tick
and a request-triggered tick), which is what makes the whole tick idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.notifications.models import (
    Notification,
    Streak,
    StreakEvent,
)


def make_dedup_key(course_id: str, module_id: str | None, kind: str) -> str:
    """Stable per-(course, module, kind) key used to emit each record once."""
    return f"{course_id}:{module_id or '-'}:{kind}"


class NotificationRepository:
    """Typed read/write access to one process's notification + streak tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Streak ───────────────────────────────────────────────────────────────

    def get_or_create_streak(self, persona_id: str) -> Streak:
        streak = self._session.get(Streak, persona_id)
        if streak is None:
            streak = Streak(persona_id=persona_id)
            self._session.add(streak)
            self._session.commit()
            self._session.refresh(streak)
        return streak

    def save_streak(self, streak: Streak) -> Streak:
        streak.updated_at = datetime.now(UTC)
        self._session.add(streak)
        self._session.commit()
        self._session.refresh(streak)
        return streak

    # ── Notifications ────────────────────────────────────────────────────────

    def upsert_notification(
        self,
        *,
        persona_id: str,
        course_id: str,
        module_id: str | None,
        kind: str,
        title: str,
        body: str,
        link: str,
    ) -> Notification | None:
        """Insert a notification, or return ``None`` if its dedup key already exists.

        Idempotent: the tick re-derives the same notifications every run, so only
        the first run for a given (course, module, kind) actually inserts.
        """
        dedup_key = make_dedup_key(course_id, module_id, kind)
        existing = self._session.exec(
            select(Notification).where(Notification.dedup_key == dedup_key)
        ).first()
        if existing is not None:
            return None
        notification = Notification(
            persona_id=persona_id,
            course_id=course_id,
            module_id=module_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            dedup_key=dedup_key,
        )
        self._session.add(notification)
        try:
            self._session.commit()
        except IntegrityError:
            # A concurrent tick inserted the same dedup_key first — treat as no-op.
            self._session.rollback()
            return None
        self._session.refresh(notification)
        return notification

    def list_notifications(self, persona_id: str, *, limit: int = 50) -> list[Notification]:
        """A persona's notifications, newest first (for the panel + poll)."""
        statement = (
            select(Notification)
            .where(Notification.persona_id == persona_id)
            .order_by(col(Notification.created_at).desc())
            .limit(limit)
        )
        return list(self._session.exec(statement).all())

    def unread_count(self, persona_id: str) -> int:
        statement = select(Notification).where(
            Notification.persona_id == persona_id,
            col(Notification.read).is_(False),
        )
        return len(list(self._session.exec(statement).all()))

    def get_notification(self, notification_id: str) -> Notification | None:
        return self._session.get(Notification, notification_id)

    def mark_read(self, notification: Notification) -> Notification:
        notification.read = True
        self._session.add(notification)
        self._session.commit()
        self._session.refresh(notification)
        return notification

    def mark_all_read(self, persona_id: str) -> int:
        """Mark every unread notification for a persona read; return how many changed."""
        statement = select(Notification).where(
            Notification.persona_id == persona_id,
            col(Notification.read).is_(False),
        )
        rows = list(self._session.exec(statement).all())
        for row in rows:
            row.read = True
            self._session.add(row)
        if rows:
            self._session.commit()
        return len(rows)

    def mark_toasted(self, notification_ids: list[str]) -> int:
        """Flag notifications as already surfaced as a live toast; return count."""
        if not notification_ids:
            return 0
        statement = select(Notification).where(col(Notification.id).in_(notification_ids))
        rows = list(self._session.exec(statement).all())
        for row in rows:
            row.toasted = True
            self._session.add(row)
        if rows:
            self._session.commit()
        return len(rows)

    # ── Scoring ledger ───────────────────────────────────────────────────────

    def has_scoring_event(self, course_id: str, module_id: str, kind: str) -> bool:
        dedup_key = make_dedup_key(course_id, module_id, kind)
        statement = select(StreakEvent).where(StreakEvent.dedup_key == dedup_key)
        return self._session.exec(statement).first() is not None

    def add_scoring_event(
        self,
        *,
        persona_id: str,
        course_id: str,
        module_id: str,
        kind: str,
        delta: int,
        occurred_at: datetime,
    ) -> StreakEvent | None:
        """Append a scoring event, or ``None`` if one already exists for this key."""
        dedup_key = make_dedup_key(course_id, module_id, kind)
        event = StreakEvent(
            persona_id=persona_id,
            course_id=course_id,
            module_id=module_id,
            kind=kind,
            delta=delta,
            dedup_key=dedup_key,
            occurred_at=occurred_at,
        )
        self._session.add(event)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            return None
        self._session.refresh(event)
        return event
