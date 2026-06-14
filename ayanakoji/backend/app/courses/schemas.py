"""Request/response DTOs for the courses API (separate from the ORM tables)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Upper bound on a single learner turn. Generous enough to paste a stack trace or
# a config block, bounded so one message can't blow the model context, balloon the
# stored transcript blob, or be used as a cheap cost/DoS amplifier (critique C2).
MAX_MESSAGE_CHARS = 8000


class CourseCreate(BaseModel):
    """Open a new chat (course) from the learner's first message."""

    persona_id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class CoursePatch(BaseModel):
    """Rename the chat and/or (un)link the Athenaeum course. Only sent fields apply."""

    chat_name: str | None = Field(default=None, min_length=1)
    catalog_id: str | None = None


class MessageIn(BaseModel):
    """A learner turn appended to the conversation."""

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class AcceptCourse(BaseModel):
    """Accept the suggested course: link it to this chat and start attempt 1."""

    catalog_id: str = Field(min_length=1, description="Athenaeum course id to enroll in")


class SetPace(BaseModel):
    """Set the study pace for this course (gates plan generation)."""

    pace: str = Field(pattern="^(slower|normal|faster)$", description="slower | normal | faster")


class ModuleRead(BaseModel):
    """One scheduled module with its progress + sequential lock state."""

    module_id: str
    title: str
    sequence: int
    estimated_minutes: int
    complete_before: str
    completed: bool
    locked: bool = Field(description="True until the prior module is completed")
    scheduled: list[dict[str, Any]]


class ModuleContentRead(BaseModel):
    """A module's rendered-ready markdown content for the Modules tab."""

    module_id: str
    title: str
    content: str


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


# ── Learner assessment session schemas (new evaluation pipeline) ──────────────


class SessionChoiceQuestionRead(BaseModel):
    """A choice question presented to the learner — correct_answers withheld."""

    id: str
    bank_question_id: str | None
    sequence: int
    prompt: str
    kind: str  # "mcq" | "msq"
    choices: list[str]
    learner_choice: list[str] | None
    submitted: bool
    is_correct: bool | None


class SessionLlmQuestionRead(BaseModel):
    """An LLM question state — reference_answer never exposed."""

    id: str
    bank_question_id: str | None
    prompt: str
    messages: list[dict[str, Any]]
    submitted: bool
    score: int | None
    reasoning: str | None
    turn_count: int
    grading_complete: bool


class AssessmentSessionRead(BaseModel):
    """Full state of one assessment session (choices or llm)."""

    id: str
    course_id: str
    module_id: str | None
    type: str
    attempt_number: int
    score: float | None
    passed: bool | None
    completed_at: datetime | None
    created_at: datetime
    choice_questions: list[SessionChoiceQuestionRead] = []
    llm_questions: list[SessionLlmQuestionRead] = []


class ModuleAssessmentSummary(BaseModel):
    """One attempt row returned by GET /modules/{mid}/assessments."""

    id: str
    type: str
    attempt_number: int
    score: float | None
    passed: bool | None
    completed_at: datetime | None
    created_at: datetime


class ChoiceSelectBody(BaseModel):
    """Save in-progress selection for a single choice question."""

    selections: list[str]


class ChoiceQuestionResult(BaseModel):
    """Per-question result after choices are submitted."""

    id: str
    sequence: int
    prompt: str
    kind: str
    choices: list[str]
    correct_answers: list[str]  # revealed after submission
    learner_choice: list[str] | None
    is_correct: bool | None


class ChoiceSubmitResult(BaseModel):
    """Returned by POST /choices/submit."""

    assessment_id: str
    score: float
    passed: bool
    questions: list[ChoiceQuestionResult]


class LlmTurnBody(BaseModel):
    """One learner reply in the LLM-grader exchange."""

    content: str = Field(min_length=1, max_length=4000)


class LlmQuestionResult(BaseModel):
    """Per-question result for LLM assessment results view."""

    id: str
    prompt: str
    score: int | None
    reasoning: str | None
    turn_count: int
    grading_complete: bool
    messages: list[dict[str, Any]]


class LlmSubmitResult(BaseModel):
    """Returned by POST /llm/submit."""

    assessment_id: str
    score: float
    passed: bool
    questions: list[LlmQuestionResult]
