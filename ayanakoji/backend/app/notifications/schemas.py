"""Typed request/response contracts for the notifications API.

These mirror the table shapes (notifications/models.py) as the wire format the
Next.js client consumes. Keep them in sync with ``frontend/src/lib/api.ts``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.notifications.models import Notification, Streak


class NotificationOut(BaseModel):
    """One notification as the frontend renders it (panel row + toast)."""

    id: str
    course_id: str
    module_id: str | None
    kind: str
    title: str
    body: str
    link: str
    read: bool
    toasted: bool
    created_at: datetime

    @classmethod
    def of(cls, n: Notification) -> NotificationOut:
        return cls(
            id=n.id,
            course_id=n.course_id,
            module_id=n.module_id,
            kind=n.kind,
            title=n.title,
            body=n.body,
            link=n.link,
            read=n.read,
            toasted=n.toasted,
            created_at=n.created_at,
        )


class StreakOut(BaseModel):
    """The persona's gamification score for the fire button."""

    persona_id: str
    points: int
    on_time_streak: int
    miss_streak: int

    @classmethod
    def of(cls, s: Streak) -> StreakOut:
        return cls(
            persona_id=s.persona_id,
            points=s.points,
            on_time_streak=s.on_time_streak,
            miss_streak=s.miss_streak,
        )


class NotificationFeed(BaseModel):
    """The single payload the poll endpoint returns: list + unread count + streak."""

    notifications: list[NotificationOut]
    unread_count: int
    streak: StreakOut


class MarkToastedRequest(BaseModel):
    """Ids the frontend has just surfaced as live toasts (so they never re-toast)."""

    ids: list[str]


class MutationResult(BaseModel):
    """How many rows a read-all / mark-toasted mutation changed."""

    changed: int
