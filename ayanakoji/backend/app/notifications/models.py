"""SQLModel tables for learner notifications and the streak score.

These live in the learner-workspace database (``athenaeum.db``) alongside the
course tables, since they're derived from a learner's own progress. Three tables:

* ``Notification`` — one surfaced message (deep-linked, dedup'd, read/toast state).
* ``Streak`` — the per-persona running gamification score (one row per persona).
* ``StreakEvent`` — an append-only ledger of every applied scoring event, so the
  cron tick can award/penalise each module exactly once (idempotency).

The cron tick is the single writer; it dedups on ``dedup_key`` (derived from the
course, module, and kind) so re-running the tick never double-counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel

# ── Notification kinds ───────────────────────────────────────────────────────
# A module was completed and a next module is now available.
KIND_NEXT_MODULE = "next_module"
# The final module was completed — the whole course is done.
KIND_COURSE_COMPLETE = "course_complete"
# A module's deadline is approaching and it isn't done yet.
KIND_DEADLINE_SOON = "deadline_soon"
# A module's deadline passed without completion.
KIND_DEADLINE_MISSED = "deadline_missed"

NOTIFICATION_KINDS = (
    KIND_NEXT_MODULE,
    KIND_COURSE_COMPLETE,
    KIND_DEADLINE_SOON,
    KIND_DEADLINE_MISSED,
)

# ── Scoring (StreakEvent) kinds ──────────────────────────────────────────────
SCORE_ON_TIME = "on_time"  # module completed on or before its deadline → +POINTS_ON_TIME
SCORE_MISSED = "missed"  # deadline passed without completion → escalating penalty

# Points awarded for an on-time module completion.
POINTS_ON_TIME = 10
# Base penalty per consecutive missed deadline (×1, ×2, ×3 → -2, -4, -6, ...).
POINTS_MISS_STEP = 2


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Notification(SQLModel, table=True):
    """One notification surfaced to a learner (cron-generated, idempotent)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    persona_id: str = Field(index=True)
    course_id: str = Field(index=True)
    module_id: str | None = Field(default=None)
    kind: str  # one of NOTIFICATION_KINDS
    title: str
    body: str
    # Frontend deep link (e.g. "/chat/<course>/modules/<module>").
    link: str
    # Stable per-(course, module, kind) key so the tick emits each notification once.
    dedup_key: str = Field(unique=True, index=True)
    # The learner has opened/acknowledged it (drives the red unread badge).
    read: bool = Field(default=False)
    # It has already been shown as a live toast (so polling never re-toasts it).
    toasted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class Streak(SQLModel, table=True):
    """A persona's running gamification score (one row per persona)."""

    persona_id: str = Field(primary_key=True)
    # Total points: +10 per on-time module, escalating penalty per missed deadline.
    points: int = Field(default=0)
    # Consecutive on-time completions (the "streak" the fire represents).
    on_time_streak: int = Field(default=0)
    # Consecutive missed deadlines — drives the -2/-4/-6 escalation; resets on-time.
    miss_streak: int = Field(default=0)
    updated_at: datetime = Field(default_factory=_now)


class StreakEvent(SQLModel, table=True):
    """Append-only ledger of applied scoring events (idempotency for the tick)."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    persona_id: str = Field(index=True)
    course_id: str
    module_id: str
    kind: str  # SCORE_ON_TIME | SCORE_MISSED
    delta: int  # points applied (positive award, negative penalty)
    # Stable per-(course, module, kind) key so a module is scored once per kind.
    dedup_key: str = Field(unique=True, index=True)
    # The event's effective moment (completion time, or the missed deadline date),
    # used to order events chronologically when recomputing the streak.
    occurred_at: datetime
    created_at: datetime = Field(default_factory=_now)


# Table names owned by the learner-workspace database — appended to init_db's scope
# so create_all builds them in athenaeum.db (not the separate assessments DB).
NOTIFICATION_TABLE_NAMES = ("notification", "streak", "streakevent")
