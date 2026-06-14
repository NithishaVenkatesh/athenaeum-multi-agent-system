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

from app.agent.assessor import grade_practice, review_practice
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


def _stream_practice_review(
    course_id: str, selections: dict[str, list[str]]
) -> Iterator[str]:
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

        yield _sse(PhaseEvent(phase=reply.telemetry).model_dump(mode="json"))
        parts: list[str] = []
        completed = False
        try:
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
