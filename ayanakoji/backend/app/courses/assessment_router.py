"""Learner-facing assessment session API.

Endpoints in this module drive the evaluation pipeline: starting a session,
answering choice questions, interacting with the LLM grader, and viewing results.
The authored question banks live in assessments.db (read-only); learner state
lives in athenaeum.db (read-write via CourseRepository).

Random sampling per session:
- Choices: 5 of 10 bank questions, different each attempt (pure random sample).
- LLM: 1 of 3 bank questions, round-robin across attempts (all 3 before repeating).

Module completion is gated: the CourseModule row is set completed=True only
when the learner has *passed* the latest attempt of BOTH choices and llm.
"""

from __future__ import annotations  # all annotations are strings at runtime

import json
import random
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.assessments.engine import get_session as get_assessment_session
from app.assessments.repository import AssessmentRepository
from app.courses.models import Assessment, ChoiceQuestion, CourseModule, LlmQuestion
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    AssessmentSessionRead,
    ChoiceQuestionResult,
    ChoiceSelectBody,
    ChoiceSubmitResult,
    LlmQuestionResult,
    LlmSubmitResult,
    LlmTurnBody,
    ModuleAssessmentSummary,
    SessionChoiceQuestionRead,
    SessionLlmQuestionRead,
)
from app.db import get_session

router = APIRouter(prefix="/api/courses", tags=["assessments"])

SessionDep = Annotated[Session, Depends(get_session)]
AssessmentSessionDep = Annotated[Session, Depends(get_assessment_session)]

PASS_THRESHOLD = 5.0  # score >= 5.0 / 10.0 → passed
CHOICES_SAMPLE = 5  # learner sees 5 of 10 bank questions per session
LLM_SAMPLE = 1  # learner answers 1 of 3 LLM questions per session


def _require_course(repo: CourseRepository, course_id: str) -> None:
    if repo.get(course_id) is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")


def _require_module(repo: CourseRepository, course_id: str, module_id: str) -> CourseModule:

    m = repo.get_module(course_id, module_id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"module '{module_id}' not in plan")
    if m.locked if hasattr(m, "locked") else False:
        raise HTTPException(status_code=403, detail="module is locked")
    return m


def _to_session_read(
    a: Assessment,
    choice_qs: list[ChoiceQuestion],
    llm_qs: list[LlmQuestion],
) -> AssessmentSessionRead:
    return AssessmentSessionRead(
        id=a.id,
        course_id=a.course_id,
        module_id=a.module_id,
        type=a.type,
        attempt_number=a.attempt_number,
        score=a.score,
        passed=a.passed,
        completed_at=a.completed_at,
        created_at=a.created_at,
        choice_questions=[
            SessionChoiceQuestionRead(
                id=q.id,
                bank_question_id=q.bank_question_id,
                sequence=q.sequence,
                prompt=q.prompt,
                kind=_choice_kind(q),
                choices=q.choices,
                learner_choice=q.learner_choice,
                submitted=q.submitted,
                is_correct=q.is_correct,
            )
            for q in choice_qs
        ],
        llm_questions=[
            SessionLlmQuestionRead(
                id=q.id,
                bank_question_id=q.bank_question_id,
                prompt=q.prompt,
                messages=q.messages,
                submitted=q.submitted,
                score=q.score,
                reasoning=q.reasoning,
                turn_count=q.turn_count,
                grading_complete=q.grading_complete,
            )
            for q in llm_qs
        ],
    )


def _choice_kind(q: ChoiceQuestion) -> str:
    # Reconstruct kind from correct_answers count (1=mcq, 2+=msq).
    return "mcq" if len(q.correct_answers) == 1 else "msq"


def _choice_credit(learner_choice: list[str], correct_answers: list[str]) -> float:
    """Proportional credit in [0, 1]: (right picks − wrong picks) / #correct, floored at 0.

    A single-answer (MCQ) question reduces to all-or-nothing. A multi-select (MSQ)
    rewards partial correctness while penalising over-selection, so 3-of-4 right with
    no wrong picks earns 0.75 of the question instead of a flat 0.
    """
    correct = set(correct_answers)
    if not correct:
        return 0.0
    chosen = set(learner_choice)
    right = len(chosen & correct)
    wrong = len(chosen - correct)
    return max(0.0, (right - wrong) / len(correct))


def _record_pass(a: Assessment) -> None:
    """Stamp the permanent success record the first time this test is passed.

    ``attempts_to_pass`` / ``passed_at`` are set once and never cleared, so a later
    failed retake cannot un-complete the module (progress is derived from these)."""
    if a.passed and a.attempts_to_pass is None:
        a.attempts_to_pass = a.attempt_number
        a.passed_at = a.completed_at or datetime.now(UTC)


def _sse(payload: dict) -> str:  # type: ignore[type-arg]
    return f"data: {json.dumps(payload)}\n\n"


# ── Module-scoped: start assessment, list attempts ───────────────────────────


@router.post(
    "/{course_id}/modules/{module_id}/assessments/start",
    response_model=AssessmentSessionRead,
    status_code=201,
    summary="Start a new choices or llm assessment session for a module",
)
def start_assessment(
    course_id: str,
    module_id: str,
    type: str,
    session: SessionDep,
    asmtsession: AssessmentSessionDep,
    force: bool = False,
) -> AssessmentSessionRead:
    """Create a new assessment attempt; samples questions from the bank.

    Returns 409 if the learner has already passed this assessment type, unless
    ``?force=true`` is passed (an explicit retake from the Evaluations tab). A
    retake samples a fresh question set and persists it as a new attempt.
    Returns 422 if the bank has no questions for this module+type.
    """
    if type not in ("choices", "llm"):
        raise HTTPException(status_code=422, detail="type must be 'choices' or 'llm'")

    repo = CourseRepository(session)
    _require_course(repo, course_id)
    mod = repo.get_module(course_id, module_id)
    if mod is None:
        raise HTTPException(status_code=404, detail=f"module '{module_id}' not in plan")

    # Sequential lock: every earlier module must be complete (derived from tests).
    modules = repo.list_modules(course_id)
    target = next((m for m in modules if m.module_id == module_id), None)
    completed_ids = repo.completed_module_ids(course_id)
    if target and any(
        m.module_id not in completed_ids for m in modules if m.sequence < target.sequence
    ):
        raise HTTPException(status_code=409, detail="complete earlier modules first")

    # Block retake if already cleared — unless an explicit retake (force) is requested,
    # in which case we fall through and sample a fresh question set below.
    if not force and repo.cleared(course_id, module_id, type):
        raise HTTPException(
            status_code=409,
            detail=f"{type} assessment already passed for this module",
        )

    # --- LLM ordering constraint: choices must be cleared before LLM starts ---
    if type == "llm" and not repo.cleared(course_id, module_id, "choices"):
        raise HTTPException(
            status_code=409,
            detail="complete the choices assessment first",
        )

    # Latest-only model: drop the prior attempt's records and carry forward the
    # running count + the permanent success record (so a retake never loses it).
    prior_count, attempts_to_pass, passed_at = repo.reset_for_new_attempt(
        course_id, module_id, type
    )
    attempt_number = prior_count + 1

    # Look up the authored bank.
    a_repo = AssessmentRepository(asmtsession)
    bank_ids = a_repo.assessment_ids_for_module(module_id)
    bank = next(
        (
            a_repo.get_bank(bid)
            for bid in bank_ids
            if a_repo.get_bank(bid) and a_repo.get_bank(bid).kind == type  # type: ignore[union-attr]
        ),
        None,
    )
    if bank is None:
        raise HTTPException(
            status_code=422,
            detail=f"no {type} bank found for module '{module_id}'",
        )

    # Create the session record (carrying the permanent success record forward).
    assessment = repo.create_assessment(
        course_id=course_id,
        module_id=module_id,
        course_module_id=mod.id,
        type=type,
        attempt_number=attempt_number,
        attempts_to_pass=attempts_to_pass,
        passed_at=passed_at,
    )

    choice_qs: list[ChoiceQuestion] = []
    llm_qs: list[LlmQuestion] = []

    if type == "choices":
        choice_bank = a_repo.choice_questions(bank.id)
        # Sample 5 of 10 randomly; different each attempt.
        sample = random.sample(choice_bank, min(CHOICES_SAMPLE, len(choice_bank)))
        for seq, cbq in enumerate(sample, 1):
            cq = ChoiceQuestion(
                assessment_id=assessment.id,
                bank_question_id=cbq.id,
                sequence=seq,
                prompt=cbq.prompt,
                choices=list(cbq.choices),
                correct_answers=list(cbq.correct_answers),
            )
            repo.add_choice_question(cq)
            choice_qs.append(cq)

    else:  # llm
        llm_bank = a_repo.llm_questions(bank.id)
        # Round-robin: prior attempt count tells us which to show next.
        prior_attempts = attempt_number - 1
        # Cycle through all 3 before repeating.
        idx = prior_attempts % len(llm_bank)
        lbq = llm_bank[idx]
        lq = LlmQuestion(
            assessment_id=assessment.id,
            bank_question_id=lbq.id,
            prompt=lbq.prompt,
        )
        repo.add_llm_question(lq)
        llm_qs.append(lq)

    return _to_session_read(assessment, choice_qs, llm_qs)


@router.get(
    "/{course_id}/modules/{module_id}/assessments",
    response_model=list[ModuleAssessmentSummary],
    summary="List all assessment attempts for a module",
)
def list_module_assessments(
    course_id: str,
    module_id: str,
    session: SessionDep,
) -> list[ModuleAssessmentSummary]:
    repo = CourseRepository(session)
    _require_course(repo, course_id)
    mod = repo.get_module(course_id, module_id)
    if mod is None:
        return []
    attempts = repo.list_module_assessments(course_id, module_id)
    return [
        ModuleAssessmentSummary(
            id=a.id,
            type=a.type,
            attempt_number=a.attempt_number,
            score=a.score,
            passed=a.passed,
            attempts_to_pass=a.attempts_to_pass,
            completed_at=a.completed_at,
            created_at=a.created_at,
        )
        for a in attempts
    ]


# ── Assessment-scoped: inspect, answer, submit ───────────────────────────────


@router.get(
    "/{course_id}/assessments/{assessment_id}",
    response_model=AssessmentSessionRead,
    summary="Full assessment session state (questions + learner answers so far)",
)
def get_assessment(
    course_id: str,
    assessment_id: str,
    session: SessionDep,
) -> AssessmentSessionRead:
    repo = CourseRepository(session)
    _require_course(repo, course_id)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    choice_qs = repo.list_choice_questions(assessment_id) if a.type == "choices" else []
    llm_qs = repo.list_llm_questions(assessment_id) if a.type == "llm" else []
    return _to_session_read(a, choice_qs, llm_qs)


@router.post(
    "/{course_id}/assessments/{assessment_id}/choices/{question_id}/select",
    response_model=SessionChoiceQuestionRead,
    summary="Save a choice selection (pre-submit, idempotent)",
)
def select_choice(
    course_id: str,
    assessment_id: str,
    question_id: str,
    body: ChoiceSelectBody,
    session: SessionDep,
) -> SessionChoiceQuestionRead:
    repo = CourseRepository(session)
    _require_course(repo, course_id)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    if a.passed is not None:
        raise HTTPException(status_code=409, detail="assessment already submitted")
    q = repo.get_choice_question(question_id)
    if q is None or q.assessment_id != assessment_id:
        raise HTTPException(status_code=404, detail="question not found")
    q.learner_choice = list(body.selections)
    repo.save_choice_question(q)
    return SessionChoiceQuestionRead(
        id=q.id,
        bank_question_id=q.bank_question_id,
        sequence=q.sequence,
        prompt=q.prompt,
        kind=_choice_kind(q),
        choices=q.choices,
        learner_choice=q.learner_choice,
        submitted=q.submitted,
        is_correct=q.is_correct,
    )


@router.post(
    "/{course_id}/assessments/{assessment_id}/choices/submit",
    response_model=ChoiceSubmitResult,
    summary="Grade all choice questions and finalise the assessment",
)
def submit_choices(
    course_id: str,
    assessment_id: str,
    session: SessionDep,
) -> ChoiceSubmitResult:
    repo = CourseRepository(session)
    _require_course(repo, course_id)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    if a.type != "choices":
        raise HTTPException(status_code=422, detail="not a choices assessment")
    if a.passed is not None:
        raise HTTPException(status_code=409, detail="already submitted")

    questions = repo.list_choice_questions(assessment_id)
    total_credit = 0.0
    results: list[ChoiceQuestionResult] = []

    for q in questions:
        credit = _choice_credit(q.learner_choice or [], q.correct_answers)
        total_credit += credit
        q.submitted = True
        q.is_correct = credit >= 1.0  # full credit only; partial counts toward score
        repo.save_choice_question(q)
        results.append(
            ChoiceQuestionResult(
                id=q.id,
                sequence=q.sequence,
                prompt=q.prompt,
                kind=_choice_kind(q),
                choices=q.choices,
                correct_answers=q.correct_answers,
                learner_choice=q.learner_choice,
                is_correct=q.is_correct,
            )
        )

    score = round((total_credit / max(len(questions), 1)) * 10, 2)
    passed = score >= PASS_THRESHOLD
    a.score = score
    a.passed = passed
    a.completed_at = datetime.now(UTC)
    _record_pass(a)
    repo.save_assessment(a)

    # A pass may complete the module (celebration only — completion is derived).
    if passed:
        _check_and_complete_module(repo, a)

    return ChoiceSubmitResult(
        assessment_id=assessment_id,
        score=score,
        passed=passed,
        questions=results,
    )


@router.get(
    "/{course_id}/assessments/{assessment_id}/results",
    response_model=ChoiceSubmitResult | LlmSubmitResult,
    summary="Full results for a completed assessment (answers revealed)",
)
def get_results(
    course_id: str,
    assessment_id: str,
    session: SessionDep,
) -> ChoiceSubmitResult | LlmSubmitResult:
    repo = CourseRepository(session)
    _require_course(repo, course_id)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    if a.passed is None:
        raise HTTPException(status_code=409, detail="assessment not yet submitted")

    if a.type == "choices":
        questions = repo.list_choice_questions(assessment_id)
        return ChoiceSubmitResult(
            assessment_id=assessment_id,
            score=a.score or 0.0,
            passed=a.passed or False,
            questions=[
                ChoiceQuestionResult(
                    id=q.id,
                    sequence=q.sequence,
                    prompt=q.prompt,
                    kind=_choice_kind(q),
                    choices=q.choices,
                    correct_answers=q.correct_answers,
                    learner_choice=q.learner_choice,
                    is_correct=q.is_correct,
                )
                for q in questions
            ],
        )
    else:
        questions_llm = repo.list_llm_questions(assessment_id)
        return LlmSubmitResult(
            assessment_id=assessment_id,
            score=a.score or 0.0,
            passed=a.passed or False,
            questions=[
                LlmQuestionResult(
                    id=q.id,
                    prompt=q.prompt,
                    score=q.score,
                    reasoning=q.reasoning,
                    turn_count=q.turn_count,
                    grading_complete=q.grading_complete,
                    messages=q.messages,
                )
                for q in questions_llm
            ],
        )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _check_and_complete_module(repo: CourseRepository, a: Assessment) -> None:
    """A pass may complete a module, and the last one completes the course.

    Completion is derived from the tests, so there is no flag to set here — the only
    side effect is the one-time course-completion celebration message.
    """
    if a.module_id and repo.module_completed(a.course_id, a.module_id):
        _maybe_celebrate(repo, a.course_id)


def _maybe_celebrate(repo: CourseRepository, course_id: str) -> None:
    """Append a celebration message when every module in the course is complete."""
    modules = repo.list_modules(course_id)
    completed = repo.completed_module_ids(course_id)
    if not modules or len(completed) < len(modules):
        return
    course = repo.get(course_id)
    if course is None:
        return
    # Avoid duplicate celebration messages.
    for msg in reversed(course.messages):
        if msg.get("role") == "assistant" and "__celebration__" in (msg.get("meta") or {}):
            return
    celebration = (
        "Great work — you've completed every module and passed all assessments! 🎓\n\n"
        "Kudos on seeing this through. Now go ace your real certification exam. "
        "Come back and tell us how it went! 🙌"
    )
    repo.append_message(
        course, role="assistant", content=celebration, meta={"__celebration__": True}
    )


@router.post(
    "/{course_id}/assessments/{assessment_id}/llm/{question_id}/turn",
    summary="Send one learner reply to the LLM grader (SSE stream)",
)
def llm_turn(
    course_id: str,
    assessment_id: str,
    question_id: str,
    body: LlmTurnBody,
    session: SessionDep,
    asmtsession: AssessmentSessionDep,
) -> StreamingResponse:
    """Append the learner's reply, run the grader, stream back the response.

    SSE events emitted:
      {type: "token", token: "..."}       — grader reply text chunks
      {type: "grade", score: N, reasoning: "..."}  — when grade_answer fires
      {type: "done"}                       — stream end

    When grade_answer is called the question is marked graded. If that was the
    last question in the assessment, the assessment is auto-submitted.
    """
    return StreamingResponse(
        _stream_llm_turn(course_id, assessment_id, question_id, body.content, session, asmtsession),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_llm_turn(
    course_id: str,
    assessment_id: str,
    question_id: str,
    content: str,
    session: Session,
    asmtsession: Session,
) -> Iterator[str]:
    """SSE generator for one grader exchange."""
    repo = CourseRepository(session)
    a_repo = AssessmentRepository(asmtsession)

    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        yield _sse({"type": "error", "message": "assessment not found"})
        return
    if a.type != "llm":
        yield _sse({"type": "error", "message": "not an llm assessment"})
        return
    if a.passed is not None:
        yield _sse({"type": "error", "message": "assessment already submitted"})
        return

    q = repo.get_llm_question(question_id)
    if q is None or q.assessment_id != assessment_id:
        yield _sse({"type": "error", "message": "question not found"})
        return
    if q.grading_complete:
        yield _sse({"type": "error", "message": "question already graded"})
        return

    # Look up the reference answer from the bank (never sent to the learner).
    bank_q = a_repo.get_llm_question_by_id(q.bank_question_id) if q.bank_question_id else None
    reference_answer = bank_q.reference_answer if bank_q else ""

    # Append the learner's message to the transcript.
    learner_msg = {"role": "user", "content": content}
    q.messages = [*q.messages, learner_msg]
    q.turn_count = q.turn_count + 1
    repo.save_llm_question(q)

    from app.agent.grader import run_turn_stream

    result = run_turn_stream(
        prompt=q.prompt,
        reference_answer=reference_answer,
        history=list(q.messages),  # includes the just-appended user turn
        turn_count=q.turn_count,
    )

    if result.grade is not None:
        # Grader produced a definitive score.
        q.score = result.grade.score
        q.reasoning = result.grade.reasoning
        q.grading_complete = True
        q.submitted = True
        q.is_correct = result.grade.score >= 5
        if result.reply:
            q.messages = [*q.messages, {"role": "assistant", "content": result.reply}]
        repo.save_llm_question(q)
        if result.reply:
            yield _sse({"type": "token", "token": result.reply})
        yield _sse(
            {
                "type": "grade",
                "score": result.grade.score,
                "reasoning": result.grade.reasoning,
            }
        )
        # Check if all questions are graded → auto-submit.
        _auto_submit_llm_if_complete(repo, a)
    else:
        # Normal text reply — append to transcript.
        reply = result.reply or "Can you elaborate further?"
        q.messages = [*q.messages, {"role": "assistant", "content": reply}]
        repo.save_llm_question(q)
        yield _sse({"type": "token", "token": reply})

    yield _sse({"type": "done"})


def _auto_submit_llm_if_complete(repo: CourseRepository, a: Assessment) -> None:
    """Submit the LLM assessment when all questions are graded."""
    qs = repo.list_llm_questions(a.id)
    if not all(q.grading_complete for q in qs):
        return
    scores = [q.score for q in qs if q.score is not None]
    avg = round(sum(scores) / max(len(scores), 1), 2)
    passed = avg >= PASS_THRESHOLD
    a.score = avg
    a.passed = passed
    a.completed_at = datetime.now(UTC)
    _record_pass(a)
    repo.save_assessment(a)
    if passed:
        _check_and_complete_module(repo, a)


@router.post(
    "/{course_id}/assessments/{assessment_id}/llm/submit",
    response_model=LlmSubmitResult,
    summary="Force-submit LLM assessment (incomplete questions score 0)",
)
def submit_llm(
    course_id: str,
    assessment_id: str,
    session: SessionDep,
) -> LlmSubmitResult:
    """Force-submit, scoring any un-graded questions as 0."""
    repo = CourseRepository(session)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    if a.type != "llm":
        raise HTTPException(status_code=422, detail="not an llm assessment")
    if a.passed is not None:
        raise HTTPException(status_code=409, detail="already submitted")

    qs = repo.list_llm_questions(assessment_id)
    for q in qs:
        if not q.grading_complete:
            q.score = 0
            q.reasoning = "Not answered."
            q.grading_complete = True
            q.submitted = True
            q.is_correct = False
            repo.save_llm_question(q)

    qs = repo.list_llm_questions(assessment_id)
    scores = [q.score for q in qs if q.score is not None]
    avg = round(sum(scores) / max(len(scores), 1), 2)
    passed = avg >= PASS_THRESHOLD
    a.score = avg
    a.passed = passed
    a.completed_at = datetime.now(UTC)
    _record_pass(a)
    repo.save_assessment(a)

    if passed:
        _check_and_complete_module(repo, a)

    return LlmSubmitResult(
        assessment_id=assessment_id,
        score=avg,
        passed=passed,
        questions=[
            LlmQuestionResult(
                id=q.id,
                prompt=q.prompt,
                score=q.score,
                reasoning=q.reasoning,
                turn_count=q.turn_count,
                grading_complete=q.grading_complete,
                messages=q.messages,
            )
            for q in qs
        ],
    )


@router.post(
    "/{course_id}/assessments/{assessment_id}/llm/start",
    response_model=SessionLlmQuestionRead,
    summary="Get the grader's opening message for the first (only) LLM question",
)
def llm_start(
    course_id: str,
    assessment_id: str,
    session: SessionDep,
) -> SessionLlmQuestionRead:
    """Generates and persists the grader's opening message, returns the question state.

    Call this once after starting an LLM assessment to get the grader's opening
    statement. The frontend renders it as the first message in the chat UI.
    """
    repo = CourseRepository(session)
    a = repo.get_assessment(assessment_id)
    if a is None or a.course_id != course_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    if a.type != "llm":
        raise HTTPException(status_code=422, detail="not an llm assessment")

    qs = repo.list_llm_questions(assessment_id)
    if not qs:
        raise HTTPException(status_code=404, detail="no questions in this assessment")
    q = qs[0]
    if q.messages:
        # Already opened — return current state.
        return SessionLlmQuestionRead(
            id=q.id,
            bank_question_id=q.bank_question_id,
            prompt=q.prompt,
            messages=q.messages,
            submitted=q.submitted,
            score=q.score,
            reasoning=q.reasoning,
            turn_count=q.turn_count,
            grading_complete=q.grading_complete,
        )

    from app.agent.grader import opening_message

    opener = opening_message(q.prompt)
    q.messages = [{"role": "assistant", "content": opener}]
    repo.save_llm_question(q)

    return SessionLlmQuestionRead(
        id=q.id,
        bank_question_id=q.bank_question_id,
        prompt=q.prompt,
        messages=q.messages,
        submitted=q.submitted,
        score=q.score,
        reasoning=q.reasoning,
        turn_count=q.turn_count,
        grading_complete=q.grading_complete,
    )
