"""HTTP surface for the learner workspace: courses (chats), messages, assessments.

A *course* and a *chat* are the same record. A new chat is created from the
learner's first message (``POST /api/courses``); subsequent turns are sent to
``POST /api/courses/{id}/messages``, which streams the assistant reply over SSE
and persists it. Assessments are modeled but not yet produced (empty list).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.catalog.loader import get_course as get_catalog_course
from app.catalog.loader import is_valid_course_id
from app.courses.models import Course
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    AssessmentRead,
    CourseCreate,
    CoursePatch,
    CourseRead,
    CourseSummary,
    MessageIn,
)
from app.courses.service import generate_title, stream_reply
from app.db import get_session, session_scope

router = APIRouter(prefix="/api/courses", tags=["courses"])

SessionDep = Annotated[Session, Depends(get_session)]


def _require(course: Course | None, course_id: str) -> Course:
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    return course


def _to_read(course: Course, repo: CourseRepository) -> CourseRead:
    linked = get_catalog_course(course.catalog_id) if course.catalog_id else None
    return CourseRead(
        id=course.id,
        persona_id=course.persona_id,
        chat_name=course.chat_name,
        catalog_id=course.catalog_id,
        catalog_title=linked.title if linked else None,
        status=course.status,
        messages=course.messages,
        assessment_ids=repo.assessment_ids(course.id),
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@router.post("", response_model=CourseRead, status_code=201, summary="Open a new chat (course)")
def create_course(body: CourseCreate, session: SessionDep) -> CourseRead:
    """Create a chat named from the first message. The message itself is sent next."""
    repo = CourseRepository(session)
    course = repo.create(persona_id=body.persona_id, chat_name=generate_title(body.content))
    return _to_read(course, repo)


@router.get("", response_model=list[CourseSummary], summary="List a persona's chats")
def list_courses(
    session: SessionDep,
    persona_id: Annotated[str, Query(min_length=1, description="Owner persona employee_id")],
) -> list[CourseSummary]:
    repo = CourseRepository(session)
    return [
        CourseSummary(
            id=c.id,
            persona_id=c.persona_id,
            chat_name=c.chat_name,
            catalog_id=c.catalog_id,
            status=c.status,
            updated_at=c.updated_at,
        )
        for c in repo.list_for_persona(persona_id)
    ]


@router.get("/{course_id}", response_model=CourseRead, summary="Full course + messages")
def get_course(course_id: str, session: SessionDep) -> CourseRead:
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    return _to_read(course, repo)


@router.patch("/{course_id}", response_model=CourseRead, summary="Rename / link a course")
def patch_course(course_id: str, body: CoursePatch, session: SessionDep) -> CourseRead:
    """Rename the chat and/or link it to an Athenaeum course (validated when set)."""
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)

    fields = body.model_fields_set
    set_catalog = "catalog_id" in fields
    if set_catalog and body.catalog_id is not None and not is_valid_course_id(body.catalog_id):
        raise HTTPException(
            status_code=422, detail=f"'{body.catalog_id}' is not an Athenaeum course id"
        )

    course = repo.update(
        course,
        chat_name=body.chat_name if "chat_name" in fields else None,
        catalog_id=body.catalog_id,
        set_catalog=set_catalog,
    )
    return _to_read(course, repo)


@router.get(
    "/{course_id}/assessments",
    response_model=list[AssessmentRead],
    summary="Course assessments (empty for now)",
)
def list_course_assessments(course_id: str, session: SessionDep) -> list[AssessmentRead]:
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    return [
        AssessmentRead(id=a.id, type=a.type, is_practice=a.is_practice, created_at=a.created_at)
        for a in repo.list_assessments(course_id)
    ]


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/{course_id}/messages", summary="Send a message; stream the reply (SSE)")
def post_message(course_id: str, body: MessageIn, session: SessionDep) -> StreamingResponse:
    """Append the learner's message, then stream the assistant reply token-by-token."""
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    # Persist the user's turn before streaming so it survives a client disconnect.
    repo.append_message(course, role="user", content=body.content)

    def event_stream() -> Iterator[str]:
        # A fresh session: the StreamingResponse body is produced after the request
        # session's transaction has done its work.
        with session_scope() as stream_session:
            stream_repo = CourseRepository(stream_session)
            current = stream_repo.get(course_id)
            if current is None:  # pragma: no cover - just persisted above
                yield _sse({"error": "course not found"})
                return
            parts: list[str] = []
            for token in stream_reply(current.messages):
                parts.append(token)
                yield _sse({"token": token})
            stream_repo.append_message(current, role="assistant", content="".join(parts))
            yield _sse({"done": True})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
