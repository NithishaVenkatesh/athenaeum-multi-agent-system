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


def make_message(role: str, content: str) -> dict[str, Any]:
    """Build one inline chat message. Roles: ``user`` | ``assistant``."""
    return {"role": role, "content": content, "created_at": _now().isoformat()}


class Course(SQLModel, table=True):
    """The chat == course record: one learner's conversation about one course."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    persona_id: str = Field(index=True)
    chat_name: str
    # Athenaeum catalog id; nullable until linked, validated against the catalog when set.
    course_id: str | None = Field(default=None)
    status: int = Field(default=STATUS_NEW)
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


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
