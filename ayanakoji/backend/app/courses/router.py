"""HTTP surface for the learner workspace: courses (chats), messages, assessments.

A *course* and a *chat* are the same record. A new chat is created from the
learner's first message (``POST /api/courses``); subsequent turns are sent to
``POST /api/courses/{id}/messages``, which streams the assistant reply over SSE
and persists it. Assessments are modeled but not yet produced (empty list).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.agent.contracts import Pace, PlanEvent, TakenCourse, TokenEvent
from app.agent.orchestrator import run_pipeline
from app.agent.state import derive_course_state
from app.catalog.content import get_module_content
from app.catalog.loader import get_course as get_catalog_course
from app.catalog.loader import is_valid_course_id
from app.courses.models import Course, CourseModule
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    AcceptCourse,
    AssessmentRead,
    CourseCreate,
    CoursePatch,
    CourseRead,
    CourseSummary,
    MessageIn,
    ModuleContentRead,
    ModuleRead,
    SetPace,
)
from app.courses.service import generate_title
from app.db import get_session, session_scope

router = APIRouter(prefix="/api/courses", tags=["courses"])

SessionDep = Annotated[Session, Depends(get_session)]

# Course.status when a learner accepts a course: attempt 1 (encoding in models.py).
STATUS_FIRST_ATTEMPT = 1


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


@router.post(
    "/{course_id}/accept",
    response_model=CourseRead,
    summary="Accept the suggested course: link it and start attempt 1",
)
def accept_course(course_id: str, body: AcceptCourse, session: SessionDep) -> CourseRead:
    """Enroll the learner: set the chat's ``catalog_id`` and bump status to attempt 1.

    Per-learner enrollment is just ``courses WHERE persona_id`` — the accepted
    course lives in the same row the chat is in, so no separate table is needed.
    """
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    if not is_valid_course_id(body.catalog_id):
        raise HTTPException(
            status_code=422, detail=f"'{body.catalog_id}' is not an Athenaeum course id"
        )
    course = repo.update(
        course,
        catalog_id=body.catalog_id,
        set_catalog=True,
        status=STATUS_FIRST_ATTEMPT,
    )
    return _to_read(course, repo)


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _taken_courses(
    repo: CourseRepository, persona_id: str, *, exclude_id: str
) -> list[TakenCourse]:
    """The learner's linked courses (their progress so far), for the recommender.

    Dedupe by catalog course, keeping the most-progressed status (negative = passed,
    which sorts lowest), so a course is counted once at its best state.
    """
    best: dict[str, int] = {}
    for course in repo.list_for_persona(persona_id):
        if course.id == exclude_id or not course.catalog_id:
            continue
        prior = best.get(course.catalog_id)
        if prior is None or course.status < prior:
            best[course.catalog_id] = course.status
    return [TakenCourse(catalog_id=cid, status=status) for cid, status in best.items()]


@router.post("/{course_id}/messages", summary="Send a message; stream the agent pipeline (SSE)")
def post_message(course_id: str, body: MessageIn, session: SessionDep) -> StreamingResponse:
    """Append the learner's turn, run it through the agent pipeline, and stream events.

    The SSE stream carries the full pipeline: per-phase telemetry, answer tokens, a
    blocked toast (jailbreak), an explicit error (providers down), and an optional
    course suggestion — every event is one of the typed ``PipelineEvent`` shapes.
    """
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
                yield _sse({"type": "error", "message": "course not found"})
                return

            taken = _taken_courses(stream_repo, current.persona_id, exclude_id=current.id)
            pace = Pace(current.pace) if current.pace else None
            existing_modules = stream_repo.list_modules(current.id)
            course_state = derive_course_state(
                catalog_id=current.catalog_id,
                pace=pace,
                module_count=len(existing_modules),
                completed_count=sum(1 for m in existing_modules if m.completed),
            )
            answer_parts: list[str] = []
            final_text = ""  # what gets persisted as the assistant turn
            plan_modules: list[dict[str, object]] | None = None
            for event in run_pipeline(
                body.content,
                persona_id=current.persona_id,
                catalog_id=current.catalog_id,
                taken=taken,
                pace=pace,
                start_date=date.today(),
                course_state=course_state,
            ):
                if isinstance(event, TokenEvent):
                    answer_parts.append(event.token)
                elif isinstance(event, PlanEvent):
                    # Persist the generated module schedule (progress system of record).
                    plan_modules = [m.model_dump(mode="json") for m in event.plan.modules]
                yield _sse(event.model_dump(mode="json"))
                # Terminal, non-token messages become the persisted transcript text.
                if event.type == "blocked":
                    final_text = event.reason
                elif event.type == "error":
                    final_text = event.message

            if plan_modules is not None:
                stream_repo.replace_modules(current.id, plan_modules)
            answer = "".join(answer_parts).strip() or final_text
            if answer:
                stream_repo.append_message(current, role="assistant", content=answer)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{course_id}/pace", response_model=CourseRead, summary="Set the study pace")
def set_pace(course_id: str, body: SetPace, session: SessionDep) -> CourseRead:
    """Set the course's pace (slower|normal|faster) — the gate before a plan is built."""
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    course.pace = body.pace
    course = repo.update(course)
    return _to_read(course, repo)


def _to_module_read(modules: list[CourseModule]) -> list[ModuleRead]:
    """Project module rows to the API shape, computing the sequential lock state."""
    out: list[ModuleRead] = []
    prev_done = True  # the first module is always available
    for m in modules:
        out.append(
            ModuleRead(
                module_id=m.module_id,
                title=m.title,
                sequence=m.sequence,
                estimated_minutes=m.estimated_minutes,
                complete_before=m.complete_before,
                completed=m.completed,
                locked=not prev_done,
                scheduled=m.scheduled,
            )
        )
        prev_done = m.completed
    return out


@router.get(
    "/{course_id}/modules",
    response_model=list[ModuleRead],
    summary="The course's scheduled modules + progress (sequential lock)",
)
def list_modules(course_id: str, session: SessionDep) -> list[ModuleRead]:
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    return _to_module_read(repo.list_modules(course_id))


@router.get(
    "/{course_id}/modules/{module_id}/content",
    response_model=ModuleContentRead,
    summary="A module's markdown content (for the Modules tab)",
)
def module_content(course_id: str, module_id: str, session: SessionDep) -> ModuleContentRead:
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    content = get_module_content(module_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"no content for module '{module_id}'")
    return ModuleContentRead(module_id=content.module_id, title=content.title, content=content.body)


@router.post(
    "/{course_id}/modules/{module_id}/complete",
    response_model=list[ModuleRead],
    summary="Mark a module complete (sequential — only the active module)",
)
def complete_module(course_id: str, module_id: str, session: SessionDep) -> list[ModuleRead]:
    """Mark the *currently available* module complete; returns the updated list.

    Sequential rule: a module can only be completed if every earlier module is
    already done (completion is by a test later; this is the manual gate for now).
    """
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    modules = repo.list_modules(course_id)
    target = next((m for m in modules if m.module_id == module_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"module '{module_id}' not in this plan")
    if any(not m.completed for m in modules if m.sequence < target.sequence):
        raise HTTPException(status_code=409, detail="complete the earlier modules first")
    repo.set_module_completed(target, completed=True)
    return _to_module_read(repo.list_modules(course_id))
