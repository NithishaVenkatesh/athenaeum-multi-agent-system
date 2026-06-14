"""Pydantic response models for the assessment-bank query API."""

from __future__ import annotations

from pydantic import BaseModel


class ChoiceQuestionRead(BaseModel):
    """A multiple-choice / multiple-select question as returned by the API."""

    id: str
    module_id: str
    prompt: str
    kind: str  # "mcq" | "msq"
    choices: list[str]
    correct_answers: list[str]


class LlmQuestionRead(BaseModel):
    """An open-ended question (with reference answer) as returned by the API."""

    id: str
    module_id: str
    prompt: str
    reference_answer: str


class AssessmentRead(BaseModel):
    """A full assessment bank: its metadata plus its questions.

    Exactly one of ``choice_questions`` / ``llm_questions`` is populated,
    determined by ``kind`` (``choices`` vs ``llm``).
    """

    id: str
    course_id: str
    module_id: str
    kind: str  # "choices" | "llm"
    title: str
    choice_questions: list[ChoiceQuestionRead] = []
    llm_questions: list[LlmQuestionRead] = []


class AssessmentIdList(BaseModel):
    """Assessment ids grouped under the key they were queried by."""

    module_id: str | None = None
    course_id: str | None = None
    assessment_ids: list[str]
