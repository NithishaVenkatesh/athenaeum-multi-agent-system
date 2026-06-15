"""Practice (formative) endpoint: grade the assessor's generated round + stream review.

The chat pipeline generates the round (questions + answer key) and persists it on the
course as ``practice_active``; this endpoint grades the learner's selections against
that server-side key, streams an honest pass / not-yet / study review, and emits the
matching CTA. Practice never writes to the Assessment table, so it never affects
official completion. Same-course turns share the chat lock so writes never interleave.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.agent.assessor import generate_practice, grade_practice, review_practice
from app.agent.contracts import DoneEvent, PhaseEvent, TokenEvent
from app.catalog.content import get_module_content
from app.courses.repository import CourseRepository
from app.courses.router import _course_lock, _sse
from app.courses.schemas import PracticeSubmit
from app.db import get_session, session_scope

router = APIRouter(prefix="/api/courses", tags=["practice"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/{course_id}/practice/submit",
    summary="Grade a practice round and stream the review (SSE)",
)
def submit_practice(course_id: str, body: PracticeSubmit, session: SessionDep) -> StreamingResponse:
    repo = CourseRepository(session)
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if not course.practice_active:
        raise HTTPException(status_code=409, detail="No active practice round to grade.")
    return StreamingResponse(
        _stream_practice_review(course_id, body.selections),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_practice_review(course_id: str, selections: dict[str, list[str]]) -> Iterator[str]:
    """SSE generator: grade against the server-side key, stream the review + CTA, clear."""
    with _course_lock(course_id), session_scope() as s:
        repo = CourseRepository(s)
        course = repo.get(course_id)
        if course is None or not course.practice_active:
            yield _sse({"type": "error", "message": "no active practice round"})
            return
        round_ = course.practice_active
        module_id = str(round_.get("module_id", ""))
        module_title = str(round_.get("title", "")) or module_id
        questions = list(round_.get("questions", []))
        content = get_module_content(module_id)
        material = (content.body[:1600] if content else "") or module_title

        repo.append_message(course, role="user", content="Here are my practice answers.")
        grade = grade_practice(questions, selections)
        reply = review_practice(
            module_id=module_id, module_title=module_title, material=material, grade=grade
        )

        parts: list[str] = []
        completed = False
        try:
            yield _sse(PhaseEvent(phase=reply.telemetry).model_dump(mode="json"))
            for token in reply.tokens:
                parts.append(token)
                yield _sse(TokenEvent(token=token).model_dump(mode="json"))
            if reply.actions is not None:
                yield _sse(reply.actions.model_dump(mode="json"))
            yield _sse(DoneEvent(route=reply.telemetry.route).model_dump(mode="json"))
            completed = True
        finally:
            # Clear the round so it can never be re-graded; persist the review turn.
            course.practice_active = {}
            repo.save(course)
            answer = "".join(parts).strip()
            if answer:
                meta: dict[str, object] = {
                    "phases": [reply.telemetry.model_dump(mode="json")],
                    "actions": reply.actions.model_dump(mode="json") if reply.actions else None,
                }
                if not completed:
                    meta["interrupted"] = True
                repo.append_message(course, role="assistant", content=answer, meta=meta)


@router.post(
    "/{course_id}/modules/{module_id}/practice/start",
    summary="Start a practice round for a specific module and stream it (SSE)",
)
def start_practice(course_id: str, module_id: str, session: SessionDep) -> StreamingResponse:
    """The module-page 'Practise' button's path: generate a round for THIS module.

    Unlike the chat 'quiz me' intent (which practises the current/first-incomplete
    module), this targets the exact module the learner opened. The module must be in
    the learner's plan. Grading is then handled by the shared submit endpoint.
    """
    repo = CourseRepository(session)
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if repo.get_module(course_id, module_id) is None:
        raise HTTPException(status_code=404, detail=f"module '{module_id}' not in this course")
    return StreamingResponse(
        _stream_practice_start(course_id, module_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_practice_start(course_id: str, module_id: str) -> Iterator[str]:
    """SSE generator: generate a round for ``module_id``, stream it, persist the key."""
    with _course_lock(course_id), session_scope() as s:
        repo = CourseRepository(s)
        course = repo.get(course_id)
        module = repo.get_module(course_id, module_id) if course else None
        if course is None or module is None:  # pragma: no cover - guarded by the route's 404
            yield _sse({"type": "error", "message": "module not found in this course"})
            return
        module_title = module.title
        repo.append_message(course, role="user", content=f"Let me practise {module_title}.")
        reply = generate_practice(module_id=module_id, module_title=module_title)

        practice_payload: dict[str, object] | None = None
        actions_payload: dict[str, object] | None = None
        parts: list[str] = []
        completed = False
        try:
            yield _sse(PhaseEvent(phase=reply.telemetry).model_dump(mode="json"))
            for token in reply.tokens:
                parts.append(token)
                yield _sse(TokenEvent(token=token).model_dump(mode="json"))
            if reply.practice is not None:
                practice_payload = reply.practice.model_dump(mode="json")  # answer key excluded
                yield _sse(practice_payload)
            if reply.actions is not None:  # only on a generation failure (go-to-module CTA)
                actions_payload = reply.actions.model_dump(mode="json")
                yield _sse(actions_payload)
            yield _sse(DoneEvent(route=reply.telemetry.route).model_dump(mode="json"))
            completed = True
        finally:
            # Persist the full round (with the key) so the submit endpoint can grade it.
            if reply.practice is not None:
                course.practice_active = {
                    "module_id": reply.practice.module_id,
                    "title": reply.practice.title,
                    "questions": [
                        {
                            "id": q.id,
                            "prompt": q.prompt,
                            "choices": list(q.choices),
                            "correct": q.correct,
                            "explanation": q.explanation,
                        }
                        for q in reply.practice.questions
                    ],
                }
                repo.save(course)
            answer = "".join(parts).strip()
            if answer:
                meta: dict[str, object] = {
                    "phases": [reply.telemetry.model_dump(mode="json")],
                    "practice": practice_payload,
                    "actions": actions_payload,
                }
                if not completed:
                    meta["interrupted"] = True
                repo.append_message(course, role="assistant", content=answer, meta=meta)
