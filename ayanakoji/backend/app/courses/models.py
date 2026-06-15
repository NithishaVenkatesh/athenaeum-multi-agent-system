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

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel

# Two kinds of assessment / question record.
ASSESSMENT_TYPES = ("llm", "choices")


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
    # Chosen study pace (slower|normal|faster); set before a plan is built.
    pace: str | None = Field(default=None)
    # Natural-language schedule edits that persist across re-plans (§schedule_edit):
    # an ISO start date and weekdays to skip.
    plan_start: str | None = Field(default=None)
    plan_excludes: list[str] = Field(default_factory=list, sa_type=JSON)
    # Plan-week numbers the learner is occupied in (e.g. "remove week 2"); the
    # planner leaves these weeks empty and flows the work into later weeks.
    plan_skip_weeks: list[int] = Field(default_factory=list, sa_type=JSON)
    # ISO date of a target exam ("my exam is July 10"); used to warn if the plan overruns it.
    plan_exam_date: str | None = Field(default=None)
    # Richer scheduling constraints the LLM scheduler agent infers, persisted so they
    # stick across re-plans: {"time_window": [lo,hi]|None, "max_session_minutes":
    # int|None, "excluded_dates": [iso,...]}. The discrete fields above hold the rest.
    plan_constraints: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    # Skill-gap check: source ("fresher"|"assessment") and per-module fraction
    # correct (module_id → 0..1). Drives the pace-gated time correction.
    skill_source: str | None = Field(default=None)
    skill_scores: dict[str, float] = Field(default_factory=dict, sa_type=JSON)
    # The sampled skill-check quiz awaiting the learner's answers (a SkillCheckRead
    # payload). Persisted so the open quiz card survives a reload / chat switch
    # instead of living only in component state; empty until a check is started,
    # cleared once it is graded or the learner marks themselves a fresher.
    skill_check_active: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    # The active practice round the assessor generated for the learner's current
    # module (questions + answer key), persisted so grading on submit reads the
    # server-side key rather than trusting the client. Empty until a round starts;
    # cleared on submit. Never written to the Assessment table, so it never affects
    # official completion / progress.
    practice_active: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    # The test a feedback turn is currently grounded on: {"module_id", "type"}.
    # Set when feedback is given (via chat or the Get Feedback button) so follow-up
    # questions stay pinned to that test; cleared the moment the learner routes
    # elsewhere. Empty until the first feedback turn. Never affects progress.
    feedback_active: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    # Staged study-plan modules awaiting the learner's approval. Promoted to real
    # CourseModule rows by POST /plan/approve; the chat path never writes modules.
    pending_modules: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class CourseModule(SQLModel, table=True):
    """A scheduled module in a course's study plan.

    Written when a plan is built (one row per module). Module *completion* is no
    longer stored here: it is derived from the assessments (a module is complete
    once both its quiz and its oral have been passed). This row only holds the
    schedule and ordering; progress lives entirely in the test results.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    module_id: str  # catalog module id, e.g. "cb-c01-m01"
    title: str
    sequence: int  # 1-based; the order modules must be done in
    estimated_minutes: int
    complete_before: str  # ISO date
    scheduled: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)


class Assessment(SQLModel, table=True):
    """A grouping of question records for one module assessment session."""

    # The latest-only model keeps at most ONE attempt row per (course, module, type):
    # a retake deletes the prior row and carries its success record forward. This DB-level
    # guard makes that invariant unbreakable — a racing second start (StrictMode double-
    # mount, or a 404-recovery force-start firing mid-flight) is rejected instead of
    # silently inserting an orphan duplicate that masks the real, passed attempt.
    __table_args__ = (
        UniqueConstraint("course_id", "module_id", "type", name="ux_assessment_course_module_type"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    course_id: str = Field(foreign_key="course.id", index=True)
    # Catalog module id (e.g. "de-c01-m01") — used to look up bank questions.
    module_id: str | None = Field(default=None, index=True)
    # FK to the CourseModule row for this learner's plan (progress tracking).
    course_module_id: str | None = Field(default=None, index=True)
    type: str  # one of ASSESSMENT_TYPES; validated at the API boundary
    is_practice: bool = Field(default=False)
    # Running attempt count for this (module, type); 1-based. Only the latest
    # attempt's question records are kept (older ones are dropped on retake), so
    # this is the count carried forward, not a row-per-attempt tally.
    attempt_number: int = Field(default=1)
    # Score 0.0–10.0 of the latest attempt (normalised regardless of question count).
    score: float | None = Field(default=None)
    # Latest attempt's result: True ≥ 5.0, False < 5.0, None = not yet submitted.
    passed: bool | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    # The permanent record of success: the attempt number at which this test was
    # FIRST passed (None until passed), and when. Set once and carried across
    # retakes, so a later failed retake never un-completes the module. This is the
    # "number of times the test was attempted to success" the progress derives from.
    attempts_to_pass: int | None = Field(default=None)
    passed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)


class ChoiceQuestion(SQLModel, table=True):
    """A multiple-choice question record for one assessment session."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    # Authored bank question id (e.g. "de-c01-m01-c01") — for traceability.
    bank_question_id: str | None = Field(default=None)
    # Display order within the assessment (1-based).
    sequence: int = Field(default=0)
    prompt: str
    choices: list[str] = Field(default_factory=list, sa_type=JSON)
    correct_answers: list[str] = Field(default_factory=list, sa_type=JSON)
    learner_choice: list[str] | None = Field(default=None, sa_type=JSON)
    submitted: bool = Field(default=False)
    is_correct: bool | None = Field(default=None)


class LlmQuestion(SQLModel, table=True):
    """An open-ended question graded by the LLM grader; transcript stored inline."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    # Authored bank question id (e.g. "de-c01-m01-l01").
    bank_question_id: str | None = Field(default=None)
    prompt: str
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    submitted: bool = Field(default=False)
    # Score 0–10 assigned by the grader; None until graded.
    score: int | None = Field(default=None)
    # Grader's brief rationale (shown to learner in results).
    reasoning: str | None = Field(default=None)
    # Number of learner reply turns so far.
    turn_count: int = Field(default=0)
    # True once the grader has called grade_answer and produced a definitive score.
    grading_complete: bool = Field(default=False)
    # Kept for compatibility with the old boolean; repurposed as score >= threshold.
    is_correct: bool | None = Field(default=None)


# The table names that belong in the learner-workspace database (athenaeum.db).
# Used to scope create_all so the separate assessments database's tables are never
# created here (they share SQLModel.metadata). Looked up from metadata by name.
COURSE_TABLE_NAMES = (
    "course",
    "coursemodule",
    "assessment",
    "choicequestion",
    "llmquestion",
)
