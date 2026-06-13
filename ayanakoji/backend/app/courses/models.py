"""SQLModel tables for the learner workspace (a course *is* a chat).

The ``Course`` is the main record — the chat and the course are the same entity.
Messages live inline as a JSON array (mirroring an ``LlmQuestion`` transcript)
rather than in a separate table, so a course carries its whole conversation.
Assessments and their question records are modeled in full now; no UI populates
them yet, but this schema is their system of record.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

# Two kinds of assessment / question record.
ASSESSMENT_TYPES = ("llm", "choices")

# ``Course.status`` encoding:
#   0   → just started, no attempt yet
#  +N   → currently on attempt N (repeated attempts, not yet passed)
#  -N   → passed on attempt N  (e.g. -2 = passed on the second attempt)
STATUS_NEW = 0


def _uuid() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


def make_message(role: str, content: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one inline chat message. Roles: ``user`` | ``assistant``.

    ``meta`` holds the assistant turn's rendered artifacts (pipeline trace,
    course choices, study plan, pace request) so they survive a reload instead
    of living only in component state.
    """
    msg: dict[str, Any] = {"role": role, "content": content, "created_at": _now().isoformat()}
    if meta:
        msg["meta"] = meta
    return msg


class Course(SQLModel, table=True):
    """The chat == course record: one learner's conversation about one course."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    persona_id: str = Field(index=True)
    chat_name: str
    # Athenaeum catalog course id this chat is about; nullable until linked, validated
    # against the catalog when set. Named ``catalog_id`` to avoid colliding with ``id``.
    catalog_id: str | None = Field(default=None)
    status: int = Field(default=STATUS_NEW)
    # Chosen study pace (slower|normal|faster); set before a plan is built.
    pace: str | None = Field(default=None)
    # Natural-language schedule edits that persist across re-plans (§schedule_edit):
    # an ISO start date and weekdays to skip.
    plan_start: str | None = Field(default=None)
    plan_excludes: list[str] = Field(default_factory=list, sa_type=JSON)
    # Plan-week numbers the learner is occupied in (e.g. "remove week 2"); the
    # planner leaves these weeks empty and flows the work into later weeks.
    plan_skip_weeks: list[int] = Field(default_factory=list, sa_type=JSON)
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class CourseModule(SQLModel, table=True):
    """A scheduled module in a course's study plan (the system of record for progress).

    Written when a plan is built (one row per module). Modules are completed
    sequentially: a module is *available* only once the prior one is completed.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    module_id: str  # catalog module id, e.g. "cb-c01-m01"
    title: str
    sequence: int  # 1-based; the order modules must be done in
    estimated_minutes: int
    complete_before: str  # ISO date
    scheduled: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    completed: bool = Field(default=False)
    completed_at: datetime | None = Field(default=None)


class Assessment(SQLModel, table=True):
    """A grouping of question records for a course; practice or evaluation."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    type: str  # one of ASSESSMENT_TYPES; validated at the API boundary
    is_practice: bool = Field(default=True)  # True = practice, False = evaluation
    created_at: datetime = Field(default_factory=_now)


class ChoiceQuestion(SQLModel, table=True):
    """A multiple-choice question record."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    prompt: str
    choices: list[str] = Field(default_factory=list, sa_type=JSON)
    correct_answers: list[str] = Field(default_factory=list, sa_type=JSON)
    learner_choice: list[str] | None = Field(default=None, sa_type=JSON)
    submitted: bool = Field(default=False)
    is_correct: bool | None = Field(default=None)


class LlmQuestion(SQLModel, table=True):
    """An open-ended question graded via an LLM exchange; transcript stored inline."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    prompt: str
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    submitted: bool = Field(default=False)
    is_correct: bool | None = Field(default=None)
