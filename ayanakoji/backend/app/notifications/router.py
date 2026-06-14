"""HTTP surface for learner notifications + the streak score.

``GET /api/notifications`` runs a lazy per-persona tick before reading, so the
feed is always current regardless of when the background cron last ran, then
returns the notifications, the unread count (red badge), and the streak (fire
button). The mutation endpoints mark notifications read (badge) and toasted (so a
live toast is shown once).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.agent.clock import today_in_timezone
from app.courses.repository import CourseRepository
from app.db import get_session
from app.notifications.cron import evaluate_persona, persona_timezone
from app.notifications.repository import NotificationRepository
from app.notifications.schemas import (
    MarkToastedRequest,
    MutationResult,
    NotificationFeed,
    NotificationOut,
    StreakOut,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

SessionDep = Annotated[Session, Depends(get_session)]


def _feed(repo: NotificationRepository, persona_id: str) -> NotificationFeed:
    return NotificationFeed(
        notifications=[NotificationOut.of(n) for n in repo.list_notifications(persona_id)],
        unread_count=repo.unread_count(persona_id),
        streak=StreakOut.of(repo.get_or_create_streak(persona_id)),
    )


@router.get("", response_model=NotificationFeed)
def get_notifications(
    session: SessionDep,
    persona_id: Annotated[str, Query(min_length=1)],
) -> NotificationFeed:
    """Lazily refresh this persona's notifications/streak, then return the feed."""
    repo = NotificationRepository(session)
    today = today_in_timezone(persona_timezone(persona_id))
    evaluate_persona(repo, CourseRepository(session), persona_id, today)
    return _feed(repo, persona_id)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(session: SessionDep, notification_id: str) -> NotificationOut:
    """Acknowledge one notification (clears it from the unread badge count)."""
    repo = NotificationRepository(session)
    notification = repo.get_notification(notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail=f"notification '{notification_id}' not found")
    return NotificationOut.of(repo.mark_read(notification))


@router.post("/read-all", response_model=MutationResult)
def mark_all_read(
    session: SessionDep,
    persona_id: Annotated[str, Query(min_length=1)],
) -> MutationResult:
    """Mark every notification for a persona as read."""
    repo = NotificationRepository(session)
    return MutationResult(changed=repo.mark_all_read(persona_id))


@router.post("/toasted", response_model=MutationResult)
def mark_toasted(session: SessionDep, payload: MarkToastedRequest) -> MutationResult:
    """Flag notifications already surfaced as live toasts so polling won't re-toast."""
    repo = NotificationRepository(session)
    return MutationResult(changed=repo.mark_toasted(payload.ids))
