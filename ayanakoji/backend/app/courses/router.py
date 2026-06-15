"""HTTP surface for the learner workspace: courses (chats), messages, assessments.

A *course* and a *chat* are the same record. A new chat is created from the
learner's first message (``POST /api/courses``); subsequent turns are sent to
``POST /api/courses/{id}/messages``, which streams the assistant reply over SSE
and persists it. Assessments are modeled but not yet produced (empty list).
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.agent.answer import answer_feedback
from app.agent.clock import today_in_timezone
from app.agent.contracts import (
    CourseProgress,
    DoneEvent,
    FeedbackResolution,
    Pace,
    PhaseEvent,
    PlanEvent,
    ProgressSnapshot,
    Route,
    ScheduledBlock,
    TakenCourse,
    TokenEvent,
)
from app.agent.orchestrator import run_pipeline
from app.agent.router_agent import (
    is_acceptance,
    is_feedback_intent,
    is_options_question,
    is_progress_intent,
    is_refusal,
)
from app.agent.schedule_edit import parse_adjustment, parse_pace
from app.agent.state import derive_course_state
from app.agent.study_plan import occupied_intervals
from app.catalog.content import get_module_content
from app.catalog.loader import get_course as get_catalog_course
from app.catalog.loader import is_valid_course_id
from app.config import get_settings
from app.courses.feedback import feedback_performance, resolve_feedback_target
from app.courses.models import Course, CourseModule
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    AcceptCourse,
    AssessmentRead,
    CourseCreate,
    CoursePatch,
    CourseRead,
    CourseSummary,
    EvaluationRead,
    MessageIn,
    ModuleContentRead,
    ModuleRead,
    SetPace,
)
from app.courses.service import generate_title
from app.db import get_session, session_scope
from app.workiq.repository import get_repository

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
        messages=course.messages,
        assessment_ids=repo.assessment_ids(course.id),
        skill_check_active=course.skill_check_active or None,
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


@router.get(
    "/{course_id}/evaluations",
    response_model=list[EvaluationRead],
    summary="The course's per-module evaluations (quiz + oral each) with lock + score",
)
def list_evaluations(course_id: str, session: SessionDep) -> list[EvaluationRead]:
    """The canonical evaluation set: two per module (choices then llm), in module order.

    Lock state mirrors ``start_assessment``: a module's evaluations open only once the
    prior module is complete (sequential), and the oral exam additionally waits on that
    module's quiz being cleared. ``completed`` means cleared (passed at least once);
    score/passed reflect the latest attempt, ``attempts_to_pass`` the success record.
    """
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    out: list[EvaluationRead] = []
    prev_done = True  # the first module's evaluations are reachable with the module
    for m in repo.list_modules(course_id):
        module_unlocked = prev_done
        choices_cleared = repo.cleared(course_id, m.module_id, "choices")
        for etype in ("choices", "llm"):
            latest = repo.latest_assessment(course_id, m.module_id, etype)
            cleared = latest is not None and latest.attempts_to_pass is not None
            locked = not module_unlocked or (etype == "llm" and not choices_cleared)
            out.append(
                EvaluationRead(
                    module_id=m.module_id,
                    module_title=m.title,
                    sequence=m.sequence,
                    type=etype,
                    locked=locked,
                    completed=cleared,
                    attempted=latest is not None,
                    score=latest.score if latest else None,
                    passed=latest.passed if latest else None,
                    attempts_to_pass=latest.attempts_to_pass if latest else None,
                    # The latest attempt's questions back the review (latest-only model).
                    review_assessment_id=(
                        latest.id
                        if latest is not None and latest.completed_at is not None
                        else None
                    ),
                    attempts=latest.attempt_number if latest else 0,
                )
            )
        prev_done = repo.module_completed(course_id, m.module_id)
    return out


@router.post(
    "/{course_id}/accept",
    response_model=CourseRead,
    summary="Accept the suggested course: link it to this chat",
)
def accept_course(course_id: str, body: AcceptCourse, session: SessionDep) -> CourseRead:
    """Enroll the learner by linking the chat's ``catalog_id``.

    Per-learner enrollment is just ``courses WHERE persona_id``; the accepted course
    lives in the same row the chat is in, so no separate table is needed. There is no
    stored status: a course is "in progress" once linked and "passed" once every
    module's tests are cleared (all derived from the assessments).
    """
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    if not is_valid_course_id(body.catalog_id):
        raise HTTPException(
            status_code=422, detail=f"'{body.catalog_id}' is not an Athenaeum course id"
        )
    # Rename the chat to the course once picked, so the sidebar reads as the course.
    linked = get_catalog_course(body.catalog_id)
    course = repo.update(
        course,
        chat_name=linked.title if linked else None,
        catalog_id=body.catalog_id,
        set_catalog=True,
    )
    return _to_read(course, repo)


def _apply_schedule_edit(
    repo: CourseRepository, course: Course, text: str, *, today: date
) -> Course:
    """Persist a natural-language schedule edit on the course (merges with prior).

    ``today`` is the learner's local date (persona timezone), so "next week" and
    "after June 30" resolve in the learner's calendar, not the server's (M4).
    The edit sticks: future plan builds reuse the start date, skipped days, and exam date.
    """
    adj = parse_adjustment(text, today=today)
    if adj is None:
        return course
    course.plan_start = adj.start_date.isoformat() if adj.start_date else course.plan_start
    course.plan_excludes = sorted(set(course.plan_excludes) | adj.exclude_days)
    course.plan_skip_weeks = sorted(set(course.plan_skip_weeks) | adj.skip_weeks)
    if adj.exam_date is not None:
        course.plan_exam_date = adj.exam_date.isoformat()
    repo.save(course)
    return course


def _persist_agent_constraints(
    repo: CourseRepository, course: Course, constraints: dict[str, object]
) -> None:
    """Persist the scheduler agent's chosen constraints onto the course (online).

    The discrete fields keep their existing meaning (read by the reserved-interval
    and state logic); the richer ones (time window, max session, excluded dates)
    live in ``plan_constraints``. This is what makes an agentic edit stick across
    re-plans, replacing the old regex persistence on the online path.
    """
    pace = constraints.get("pace")
    if isinstance(pace, str):
        course.pace = pace
    start = constraints.get("start_date")
    if isinstance(start, str):
        course.plan_start = start
    exclude = constraints.get("exclude_days")
    if isinstance(exclude, list):
        course.plan_excludes = sorted(str(d) for d in exclude)
    skip = constraints.get("skip_weeks")
    if isinstance(skip, list):
        course.plan_skip_weeks = sorted(int(w) for w in skip if isinstance(w, int))
    exam = constraints.get("exam_date")
    course.plan_exam_date = exam if isinstance(exam, str) else None
    course.plan_constraints = {
        "time_window": constraints.get("time_window"),
        "max_session_minutes": constraints.get("max_session_minutes"),
        "excluded_dates": constraints.get("excluded_dates") or [],
    }
    repo.save(course)


def _pace_choice_pending(course: Course) -> bool:
    """True when the last assistant turn asked for a pace and none is set yet.

    While a pace decision is outstanding the learner must pick it with the pace
    buttons (POST /pace), not by typing — a human-in-the-loop gate (HITL). Course
    *suggestions* are deliberately not gated: a learner can keep typing while
    choosing a course. Picking a pace clears this (course.pace is then set).
    """
    if course.pace:
        return False
    for message in reversed(course.messages):
        if message.get("role") == "assistant":
            return bool((message.get("meta") or {}).get("pace_request"))
    return False


# Ordinal words → option index, so "the second one" / "the latter" resolves a choice.
_ORDINAL_INDEX = {
    "first": 0, "1st": 0, "former": 0, "second": 1, "2nd": 1, "latter": 1, "third": 2,
    "3rd": 2, "fourth": 3, "4th": 3, "fifth": 4, "5th": 4, "last": -1,
}  # fmt: skip
_ORDINAL_NUM_RE = re.compile(r"\b(?:number|option|the)\s+(\d+)\b|\b(\d+)(?:st|nd|rd|th)\b")


def _last_suggestion_options(course: Course) -> list[dict[str, object]]:
    """The course options the last assistant turn offered (newest turn wins)."""
    for message in reversed(course.messages):
        if message.get("role") == "assistant":
            return ((message.get("meta") or {}).get("suggestion") or {}).get("options") or []
    return []


def _resolve_suggestion_choice(course: Course, content: str) -> str | None:
    """Catalog id the learner picked from the last suggestion, by accept / ordinal / name.

    Handles "yes, start that one" (single option), "the second one" / "number 2" /
    "the latter" (positional), and naming the course/title. Returns None when the chat
    is already linked, nothing was offered, or a bare "yes" is ambiguous (many options).
    """
    if course.catalog_id:
        return None
    options = _last_suggestion_options(course)
    if not options:
        return None
    # A refusal ("absolutely not", "please don't") selects nothing — never enroll on it.
    if is_refusal(content):
        return None
    # A comparison / info question about the options ("what's the difference between the
    # first and the second one?") names ordinals but is not a selection — enrolling on it
    # would be a silent, persisted side-effect. An explicit accept ("let's go with the
    # second, tell me more") still selects.
    if not is_acceptance(content) and is_options_question(content):
        return None
    low = content.lower()
    offered = {str(o.get("catalog_id") or "").lower() for o in options}
    # If the learner names a DIFFERENT course id not in the offer ("start as-c03 instead"),
    # don't force-enroll the offered one; let the turn handle the newly-named course.
    for m in re.finditer(r"\b[a-z]{2}-c\d+\b", low):
        if m.group(0) not in offered:
            return None

    def _cid(index: int) -> str | None:
        try:
            return str((options[index] or {}).get("catalog_id") or "") or None
        except IndexError:
            return None

    for word, index in _ORDINAL_INDEX.items():
        if re.search(rf"\b{word}\b", low):
            return _cid(index)
    num = _ORDINAL_NUM_RE.search(low)
    if num:
        n = int(num.group(1) or num.group(2))
        if 1 <= n <= len(options):
            return _cid(n - 1)
    for option in options:
        cid = str(option.get("catalog_id") or "").lower()
        title = str(option.get("title") or "").lower()
        if (cid and cid in low) or (title and title in low):
            return str(option.get("catalog_id") or "") or None
    if len(options) == 1 and is_acceptance(content):
        return _cid(0)
    return None


def _conversation_context(course: Course) -> tuple[list[dict[str, str]], str | None]:
    """Recent turns + what the last assistant turn proposed (for follow-up routing).

    ``pending`` is "pace" when the last assistant turn asked the pace, or "suggestion"
    when it offered course(s) to start, so a follow-up ("yes", "the second one")
    resolves to accepting/building instead of being read as a fresh greeting.
    """
    history = [
        {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
        for m in course.messages
        if m.get("content")
    ]
    pending: str | None = None
    for message in reversed(course.messages):
        if message.get("role") == "assistant":
            meta = message.get("meta") or {}
            if meta.get("pace_request"):
                pending = "pace"
            elif not course.catalog_id and _last_suggestion_options(course):
                pending = "suggestion"
            break
    return history, pending


def _sse(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# One lock per course id, so two turns for the *same* course (double-click, two
# tabs) are processed one at a time. Without this, both turns read-modify-write
# the messages JSON blob and the module table concurrently and silently lose
# updates / double-book the calendar (critique C4). Different courses never block
# each other. The dict grows by one small lock per course ever touched (bounded
# by the catalog size in practice); a process restart clears it.
_course_locks_guard = threading.Lock()
_course_locks: dict[str, threading.Lock] = {}


def _course_lock(course_id: str) -> threading.Lock:
    with _course_locks_guard:
        lock = _course_locks.get(course_id)
        if lock is None:
            lock = threading.Lock()
            _course_locks[course_id] = lock
        return lock


def _course_passed(repo: CourseRepository, course: Course) -> bool:
    """A course is passed once it has modules and every one of them is complete."""
    modules = repo.list_modules(course.id)
    return bool(modules) and all(repo.module_completed(course.id, m.module_id) for m in modules)


def _taken_courses(
    repo: CourseRepository, persona_id: str, *, exclude_id: str
) -> list[TakenCourse]:
    """The learner's linked courses (their progress so far), for the recommender.

    Dedupe by catalog course, keeping it passed if it's passed in any chat, so a
    course counts once at its best state. ``passed`` is derived from the tests now.
    """
    best: dict[str, bool] = {}
    for course in repo.list_for_persona(persona_id):
        if course.id == exclude_id or not course.catalog_id:
            continue
        passed = _course_passed(repo, course)
        best[course.catalog_id] = best.get(course.catalog_id, False) or passed
    return [TakenCourse(catalog_id=cid, passed=passed) for cid, passed in best.items()]


def _course_progress_list(
    repo: CourseRepository, persona_id: str, current: Course
) -> list[CourseProgress]:
    """Per-course enrollment + next module across the persona's chats (deduped by catalog).

    Most-recent chat wins per catalog course. The next module is the first not-yet-
    completed module in sequence (completion derived from tests). All the learner's own.
    """
    out: list[CourseProgress] = []
    seen: set[str] = set()
    for course in repo.list_for_persona(persona_id):  # most-recently-updated first
        if not course.catalog_id or course.catalog_id in seen:
            continue
        seen.add(course.catalog_id)
        node = get_catalog_course(course.catalog_id)
        modules = repo.list_modules(course.id)
        done = repo.completed_module_ids(course.id)
        nxt = next(
            (m for m in sorted(modules, key=lambda m: m.sequence) if m.module_id not in done),
            None,
        )
        out.append(
            CourseProgress(
                catalog_id=course.catalog_id,
                title=node.title if node else course.catalog_id,
                passed=bool(modules) and len(done) >= len(modules),
                modules_total=len(modules),
                modules_completed=len(done),
                next_module_title=nxt.title if nxt else None,
                next_module_due=nxt.complete_before if nxt else None,
                is_current=course.id == current.id,
            )
        )
    return out


def _progress_snapshot(
    taken: list[TakenCourse],
    current: Course,
    *,
    module_count: int,
    completed_count: int,
    repo: CourseRepository | None = None,
    detailed: bool = False,
) -> ProgressSnapshot:
    """The learner's own completion status, from data already gathered this turn.

    Cheap path (every turn): ``taken`` already dedupes the persona's OTHER courses by
    catalog; fold in THIS chat's course so a 'how many courses' count includes it once.
    Detailed path (only when the turn is a progress/enrollment question): also build the
    per-course list with next modules. All the learner's own data.
    """
    node = get_catalog_course(current.catalog_id) if current.catalog_id else None
    current_title = node.title if node else None
    if detailed and repo is not None:
        courses = _course_progress_list(repo, current.persona_id, current)
        return ProgressSnapshot(
            courses_total=len(courses),
            courses_completed=sum(1 for c in courses if c.passed),
            current_title=current_title,
            courses=courses,
        )
    best: dict[str, bool] = {t.catalog_id: t.passed for t in taken}
    if current.catalog_id:
        current_passed = module_count > 0 and completed_count >= module_count
        best[current.catalog_id] = best.get(current.catalog_id, False) or current_passed
    return ProgressSnapshot(
        courses_total=len(best),
        courses_completed=sum(1 for passed in best.values() if passed),
        current_title=current_title,
    )


def _registered_courses(
    repo: CourseRepository, persona_id: str, *, exclude_id: str
) -> dict[str, tuple[str, str]]:
    """Catalog course → (chat id, chat title) for the persona's *other* linked chats.

    Lets a turn detect that an explicitly-asked course already lives in another
    chat and point the learner there instead of opening a duplicate. Most-recent
    chat wins when a course somehow appears in more than one.
    """
    out: dict[str, tuple[str, str]] = {}
    for course in repo.list_for_persona(persona_id):  # most-recently-updated first
        if course.id == exclude_id or not course.catalog_id:
            continue
        out.setdefault(course.catalog_id, (course.id, course.chat_name))
    return out


def _reserved_intervals(
    repo: CourseRepository, persona_id: str, *, exclude_id: str, today: date
) -> frozenset[tuple[str, int, int]]:
    """Absolute (date, start, end) calendar time the persona's *other* course plans use.

    Each module block is resolved to a real date via that course's own start, so
    the planner for this chat schedules around time already committed elsewhere
    and two chats never double-book the same slot. Completed modules are excluded:
    once a module is done its hours are freed up for other courses.
    """
    intervals: set[tuple[str, int, int]] = set()
    for course in repo.list_for_persona(persona_id):
        if course.id == exclude_id or not course.catalog_id:
            continue
        course_start = date.fromisoformat(course.plan_start) if course.plan_start else today
        done = repo.completed_module_ids(course.id)  # completed modules free their hours
        blocks = [
            ScheduledBlock(
                week=int(b["week"]),
                day=str(b["day"]),
                start=str(b["start"]),
                end=str(b["end"]),
                minutes=int(b.get("minutes", 0)),
            )
            for module in repo.list_modules(course.id)
            if module.module_id not in done
            for b in module.scheduled
        ]
        intervals |= occupied_intervals(course_start, blocks)
    return frozenset(intervals)


@router.post("/{course_id}/messages", summary="Send a message; stream the agent pipeline (SSE)")
def post_message(course_id: str, body: MessageIn, session: SessionDep) -> StreamingResponse:
    """Append the learner's turn, run it through the agent pipeline, and stream events.

    The SSE stream carries the full pipeline: per-phase telemetry, answer tokens, a
    blocked toast (jailbreak), an explicit error (providers down), and an optional
    course suggestion, every event is one of the typed ``PipelineEvent`` shapes.
    """
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    # HITL gate: while a pace choice is outstanding the learner must use the pace
    # buttons (POST /pace), not free text (critique HITL). 409 tells the client to
    # resolve the pending choice via its control.
    if _pace_choice_pending(course):
        raise HTTPException(
            status_code=409,
            detail="Pick a pace with the buttons above to continue.",
        )
    return StreamingResponse(
        _stream_turn(course_id, body.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_turn(course_id: str, content: str) -> Iterator[str]:
    """SSE event generator for one learner turn (module-level so it is unit-testable).

    Held under a per-course lock so concurrent turns for the same course are
    serialized (critique C4): the user-append, plan rebuild, and assistant-append
    are one atomic read-modify-write per turn, never interleaved.

    Runs in its own session because the StreamingResponse body is produced after
    the request session's work is done. The assistant turn is persisted in a
    ``finally`` so a mid-stream client disconnect still flushes the partial answer
    and any artifacts produced so far, instead of leaving a user turn with no
    assistant reply (critique C1).
    """
    with _course_lock(course_id), session_scope() as stream_session:
        stream_repo = CourseRepository(stream_session)
        current = stream_repo.get(course_id)
        if current is None:  # pragma: no cover - guarded by the 404 in post_message
            yield _sse({"type": "error", "message": "course not found"})
            return
        # Persist the learner's turn first, inside the lock, so it is part of the
        # same serialized read-modify-write as the assistant reply below.
        current = stream_repo.append_message(current, role="user", content=content)

        # Anchor every date to the learner's local "today" (persona timezone), not
        # the server's, so relative edits and plan start dates land on the learner's
        # calendar day (critique M4).
        persona = get_repository().get_persona(current.persona_id)
        today = today_in_timezone(persona.timezone if persona else None)

        taken = _taken_courses(stream_repo, current.persona_id, exclude_id=current.id)
        registered = _registered_courses(stream_repo, current.persona_id, exclude_id=current.id)
        reserved = _reserved_intervals(
            stream_repo, current.persona_id, exclude_id=current.id, today=today
        )
        # Online, the LLM scheduler agent extracts scheduling intent from free text
        # (no regex). The deterministic regex parsers are the OFFLINE fallback only,
        # since the mock has no model to interpret natural language.
        offline = get_settings().llm_offline
        if offline:
            requested_pace = parse_pace(content)
            if requested_pace is not None and current.catalog_id:
                current.pace = requested_pace.value
                stream_repo.save(current)
            current = _apply_schedule_edit(stream_repo, current, content, today=today)
        pace = Pace(current.pace) if current.pace else None
        start_date = date.fromisoformat(current.plan_start) if current.plan_start else today
        exclude_days = frozenset(current.plan_excludes)
        skip_weeks = frozenset(current.plan_skip_weeks)
        exam_date = date.fromisoformat(current.plan_exam_date) if current.plan_exam_date else None
        skill_source = current.skill_source
        skill_scores = current.skill_scores or None
        # Recent turns + the pending action (e.g. a pace question) for follow-ups
        # like a bare "yes". The trailing turn is the current message itself.
        history, pending = _conversation_context(current)
        history = history[:-1] if history else []
        # Conversational course accept (R2): "yes, start that one" / "the second one"
        # after a suggestion links the chosen course here, like the suggestion button.
        if pending == "suggestion":
            suggested = _resolve_suggestion_choice(current, content)
            if suggested and is_valid_course_id(suggested):
                linked = get_catalog_course(suggested)
                current.catalog_id = suggested
                if linked is not None:
                    current.chat_name = linked.title
                stream_repo.save(current)
        existing_modules = stream_repo.list_modules(current.id)
        completed_ids = stream_repo.completed_module_ids(current.id)  # derived from tests
        course_state = derive_course_state(
            catalog_id=current.catalog_id,
            pace=pace,
            skill_source=skill_source,
            module_count=len(existing_modules),
            completed_count=len(completed_ids),
            # Pass ids so a shrunk re-plan can't auto-complete from a stale count: completion
            # is len(passed ∩ current plan), not a raw count carried from the old module set.
            module_ids=frozenset(m.module_id for m in existing_modules),
            passed_ids=frozenset(completed_ids),
        )
        answer_parts: list[str] = []
        final_text = ""  # what gets persisted as the assistant turn
        plan_modules: list[dict[str, object]] | None = None
        # Collect the turn's rendered artifacts so they survive a reload.
        phases: list[dict[str, object]] = []
        meta_suggestion: dict[str, object] | None = None
        meta_plan: dict[str, object] | None = None
        meta_pace: dict[str, object] | None = None
        meta_skill_gate: dict[str, object] | None = None
        meta_new_chat: dict[str, object] | None = None
        meta_practice: dict[str, object] | None = None
        meta_actions: dict[str, object] | None = None
        practice_state: dict[str, object] | None = None
        agent_constraints: dict[str, object] | None = None
        modules_as_dicts: list[dict[str, object]] = [
            {
                "module_id": m.module_id,
                "title": m.title,
                "sequence": m.sequence,
                "complete_before": m.complete_before,
                "scheduled": m.scheduled,
                "completed": m.module_id in completed_ids,
            }
            for m in existing_modules
        ]
        # The learner's own completion status, for a "how much have I done?" turn.
        # Build the richer per-course list only when the turn actually asks about
        # progress / enrollment (keeps unrelated turns from paying the extra reads).
        progress = _progress_snapshot(
            taken,
            current,
            module_count=len(existing_modules),
            completed_count=len(completed_ids),
            repo=stream_repo,
            detailed=is_progress_intent(content),
        )
        # In-chat feedback: resolve which test the ask is about (DB-bound) only when the
        # turn is a feedback ask or a feedback context is pinned. ``feedback_active``
        # also lets the router keep follow-ups grounded on that test. Other linked
        # courses' titles drive the cross-course redirect.
        feedback_active = bool(current.feedback_active)
        feedback_res: FeedbackResolution | None = None
        if is_feedback_intent(content) or feedback_active:
            other_titles = [title for (_id, title) in registered.values()]
            feedback_res = resolve_feedback_target(
                stream_repo,
                current,
                content,
                modules=modules_as_dicts,
                other_course_titles=other_titles,
                active=current.feedback_active or None,
            )
        final_route: Route | None = None
        completed = False
        try:
            for event in run_pipeline(
                content,
                persona_id=current.persona_id,
                catalog_id=current.catalog_id,
                taken=taken,
                registered=registered,
                reserved=reserved,
                pace=pace,
                skill_source=skill_source,
                skill_scores=skill_scores,
                start_date=start_date,
                exclude_days=exclude_days,
                skip_weeks=skip_weeks,
                exam_date=exam_date,
                plan_constraints=current.plan_constraints or None,
                modules=modules_as_dicts,
                progress=progress,
                feedback=feedback_res,
                feedback_active=feedback_active,
                course_state=course_state,
                history=history or None,
                pending=pending,
            ):
                payload = event.model_dump(mode="json")
                if isinstance(event, TokenEvent):
                    answer_parts.append(event.token)
                elif isinstance(event, PlanEvent):
                    plan_modules = [m.model_dump(mode="json") for m in event.plan.modules]
                    meta_plan = payload["plan"]
                    agent_constraints = event.constraints
                elif event.type == "phase":
                    phases.append(payload["phase"])
                elif event.type == "suggestion":
                    meta_suggestion = {
                        "prompt": payload["prompt"],
                        "options": payload["options"],
                    }
                elif event.type == "pace_request":
                    meta_pace = payload
                elif event.type == "skill_gate_request":
                    meta_skill_gate = payload
                elif event.type == "new_chat":
                    meta_new_chat = payload
                elif event.type == "practice":
                    # payload is the client-safe dump (answer key excluded). The full
                    # round, with the key, is read off the live event for grading.
                    meta_practice = payload
                    practice_state = {
                        "module_id": event.module_id,
                        "title": event.title,
                        "questions": [
                            {
                                "id": q.id,
                                "prompt": q.prompt,
                                "choices": list(q.choices),
                                "correct": q.correct,
                                "explanation": q.explanation,
                            }
                            for q in event.questions
                        ],
                    }
                elif event.type == "action":
                    meta_actions = payload
                elif event.type == "done":
                    final_route = event.route  # to set/clear the feedback pin below
                yield _sse(payload)
                # Terminal, non-token messages become the persisted transcript text.
                if event.type == "blocked":
                    final_text = event.reason
                elif event.type == "error":
                    final_text = event.message
            completed = True
        finally:
            # No `yield` may run here — the generator may be mid-teardown.
            if plan_modules is not None:
                # Stage the previewed plan; it becomes real modules only on approval
                # (POST /plan/approve). The chat path never writes the schedule.
                current.pending_modules = plan_modules
                stream_repo.save(current)
            # Persist the constraints the scheduler agent chose so the edit sticks
            # across re-plans (the online replacement for the regex persistence).
            if agent_constraints:
                _persist_agent_constraints(stream_repo, current, agent_constraints)
            if practice_state is not None:
                current.practice_active = practice_state
                stream_repo.save(current)
            # Feedback pin: a feedback turn that answered a specific test pins it so the
            # next questions stay grounded; any other route (or a redirect/none) clears
            # it, so "answer my questions from there on" ends when the learner moves on.
            new_pin: dict[str, object] = {}
            if (
                final_route is Route.FEEDBACK
                and feedback_res is not None
                and feedback_res.kind == "answer"
            ):
                new_pin = {"module_id": feedback_res.module_id, "type": feedback_res.type}
            if (current.feedback_active or {}) != new_pin:
                current.feedback_active = new_pin
                stream_repo.save(current)
            answer = "".join(answer_parts).strip() or final_text
            if answer:
                meta: dict[str, object] = {
                    "phases": phases,
                    "suggestion": meta_suggestion,
                    "plan": meta_plan,
                    "pace_request": meta_pace,
                    "skill_gate": meta_skill_gate,
                    "new_chat": meta_new_chat,
                    "practice": meta_practice,
                    "actions": meta_actions,
                }
                if not completed:
                    meta["interrupted"] = True
                stream_repo.append_message(current, role="assistant", content=answer, meta=meta)


# ── Assessment feedback (in-chat, grounded, bypasses the topic gate) ─────────────


@router.post(
    "/{course_id}/modules/{module_id}/feedback",
    summary="Grounded feedback on the latest assessment, streamed into the chat (SSE)",
)
def post_feedback(
    course_id: str, module_id: str, type: str, session: SessionDep
) -> StreamingResponse:
    """Stream tutor feedback on the learner's latest quiz/oral attempt for a module.

    This is the 'Get Feedback' button's path. It does NOT run through the chat
    pipeline's topic gate: a generic "why did I fail my quiz" question has none of
    the module's vocabulary, so grounding rejects it and the answer agent refuses.
    Here the request is first-party and scoped, grounded in the module's own material
    plus the learner's actual answers, so the feedback is specific and never refused.
    """
    if type not in ("choices", "llm"):
        raise HTTPException(status_code=422, detail="type must be 'choices' or 'llm'")
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    return StreamingResponse(
        _stream_feedback(course_id, module_id, type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_feedback(course_id: str, module_id: str, type: str) -> Iterator[str]:
    """SSE generator for one feedback turn; persists both turns like a normal chat turn."""
    label = "quiz" if type == "choices" else "oral exam"
    with _course_lock(course_id), session_scope() as s:
        repo = CourseRepository(s)
        course = repo.get(course_id)
        if course is None:  # pragma: no cover - guarded by post_feedback's 404
            yield _sse({"type": "error", "message": "course not found"})
            return
        mod = repo.get_module(course_id, module_id)
        module_title = mod.title if mod else module_id
        # Persist a readable learner turn so the thread reads naturally on reload.
        request_text = f"Can you give me feedback on my {label} for {module_title}?"
        repo.append_message(course, role="user", content=request_text)
        # Pin this test so follow-up questions in the chat stay grounded on it, exactly
        # as a typed feedback ask would (the button and chat paths share the pin).
        course.feedback_active = {"module_id": module_id, "type": type}
        repo.save(course)

        # The module's own material grounds the feedback (trimmed for the prompt budget).
        content = get_module_content(module_id)
        material = (content.body[:1600] if content else "") or module_title

        score: float | None = None
        passed: bool | None = None
        performance = ""
        latest = repo.latest_assessment(course_id, module_id, type)
        if latest is not None and latest.completed_at is not None:
            score, passed = latest.score, latest.passed
            performance = feedback_performance(repo, latest, type)

        reply = answer_feedback(
            module_id=module_id,
            module_title=module_title,
            course_title=course.chat_name,
            material=material,
            kind=type,
            score=score,
            passed=passed,
            performance=performance,
        )

        yield _sse(PhaseEvent(phase=reply.telemetry).model_dump(mode="json"))
        parts: list[str] = []
        completed = False
        try:
            for token in reply.tokens:
                parts.append(token)
                yield _sse(TokenEvent(token=token).model_dump(mode="json"))
            yield _sse(DoneEvent(route=reply.telemetry.route).model_dump(mode="json"))
            completed = True
        finally:
            answer = "".join(parts).strip()
            if answer:
                meta: dict[str, object] = {
                    "phases": [reply.telemetry.model_dump(mode="json")],
                    "sources": [src.model_dump(mode="json") for src in reply.sources],
                }
                if not completed:
                    meta["interrupted"] = True
                repo.append_message(course, role="assistant", content=answer, meta=meta)


@router.post("/{course_id}/pace", response_model=CourseRead, summary="Set the study pace")
def set_pace(course_id: str, body: SetPace, session: SessionDep) -> CourseRead:
    """Set the course's pace (slower|normal|faster), the gate before a plan is built."""
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    course.pace = body.pace
    course = repo.update(course)
    return _to_read(course, repo)


@router.post(
    "/{course_id}/plan/approve",
    response_model=list[ModuleRead],
    summary="Approve the staged study plan: write its modules + deadlines",
)
def approve_plan(course_id: str, session: SessionDep) -> list[ModuleRead]:
    """Promote the previewed plan (``Course.pending_modules``) to real modules.

    This is the only path that writes ``CourseModule`` rows / deadlines — the chat
    path stages a preview and waits for this explicit approval (the learner's
    'put it on my schedule' confirmation). Staging is then cleared.
    """
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    pending = course.pending_modules or []
    if not pending:
        raise HTTPException(status_code=409, detail="No plan to approve — build one first.")
    repo.replace_modules(course_id, pending)
    course.pending_modules = []
    repo.save(course)
    return _to_module_read(repo, course_id, repo.list_modules(course_id))


def _to_module_read(
    repo: CourseRepository, course_id: str, modules: list[CourseModule]
) -> list[ModuleRead]:
    """Project module rows to the API shape, deriving completion + the sequential lock.

    ``completed`` is no longer stored: a module is complete once both its quiz and
    oral are cleared. The lock is still sequential — a module opens once the prior
    one is complete.
    """
    out: list[ModuleRead] = []
    prev_done = True  # the first module is always available
    for m in modules:
        completed = repo.module_completed(course_id, m.module_id)
        out.append(
            ModuleRead(
                module_id=m.module_id,
                title=m.title,
                sequence=m.sequence,
                estimated_minutes=m.estimated_minutes,
                complete_before=m.complete_before,
                completed=completed,
                locked=not prev_done,
                scheduled=m.scheduled,
            )
        )
        prev_done = completed
    return out


@router.get(
    "/{course_id}/modules",
    response_model=list[ModuleRead],
    summary="The course's scheduled modules + progress (sequential lock)",
)
def list_modules(course_id: str, session: SessionDep) -> list[ModuleRead]:
    repo = CourseRepository(session)
    _require(repo.get(course_id), course_id)
    return _to_module_read(repo, course_id, repo.list_modules(course_id))


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
