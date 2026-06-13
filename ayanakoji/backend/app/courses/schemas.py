"""Request/response DTOs for the courses API (separate from the ORM tables)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    """Open a new chat (course) from the learner's first message."""

    persona_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


class CoursePatch(BaseModel):
    """Rename the chat and/or (un)link the Athenaeum course. Only sent fields apply."""

    chat_name: str | None = Field(default=None, min_length=1)
    catalog_id: str | None = None


class MessageIn(BaseModel):
    """A learner turn appended to the conversation."""

    content: str = Field(min_length=1)


class CourseSummary(BaseModel):
    """Compact row for the course (chat) chooser."""

    id: str
    persona_id: str
    chat_name: str
    catalog_id: str | None
    status: int
    updated_at: datetime


class CourseRead(BaseModel):
    """Full course record: conversation + linked-course context + assessment ids."""

    id: str
    persona_id: str
    chat_name: str
    catalog_id: str | None
    catalog_title: str | None
    status: int
    messages: list[dict[str, Any]]
    assessment_ids: list[str]
    created_at: datetime
    updated_at: datetime


class AssessmentRead(BaseModel):
    """An assessment belonging to a course (empty list for now — schema is ready)."""

    id: str
    type: str
    is_practice: bool
    created_at: datetime
