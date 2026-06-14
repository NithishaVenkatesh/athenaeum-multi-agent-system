"""GET-only HTTP surface for the assessment question banks.

Three reads, matching the spec: pull an assessment (bank) by id, list assessment
ids by module, and list assessment ids by course. Read-only; the banks are
authored content seeded from JSON.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.assessments.engine import get_session
from app.assessments.models import AssessmentBank
from app.assessments.repository import AssessmentRepository
from app.assessments.schemas import (
    AssessmentRead,
    ChoiceQuestionRead,
    LlmQuestionRead,
)

router = APIRouter(prefix="/api/assessments", tags=["assessments"])

SessionDep = Annotated[Session, Depends(get_session)]


def _to_read(repo: AssessmentRepository, bank: AssessmentBank) -> AssessmentRead:
    """Assemble a bank plus its questions into the API read model."""
    choice_questions: list[ChoiceQuestionRead] = []
    llm_questions: list[LlmQuestionRead] = []
    if bank.kind == "choices":
        choice_questions = [
            ChoiceQuestionRead(
                id=q.id,
                module_id=q.module_id,
                prompt=q.prompt,
                kind=q.kind,
                choices=q.choices,
                correct_answers=q.correct_answers,
            )
            for q in repo.choice_questions(bank.id)
        ]
    else:
        llm_questions = [
            LlmQuestionRead(
                id=q.id,
                module_id=q.module_id,
                prompt=q.prompt,
                reference_answer=q.reference_answer,
            )
            for q in repo.llm_questions(bank.id)
        ]
    return AssessmentRead(
        id=bank.id,
        course_id=bank.course_id,
        module_id=bank.module_id,
        kind=bank.kind,
        title=bank.title,
        choice_questions=choice_questions,
        llm_questions=llm_questions,
    )


@router.get("/{assessment_id}", response_model=AssessmentRead, summary="Pull an assessment by id")
def get_assessment(assessment_id: str, session: SessionDep) -> AssessmentRead:
    """Return one assessment bank and its questions, or 404 if it doesn't exist."""
    repo = AssessmentRepository(session)
    bank = repo.get_bank(assessment_id)
    if bank is None:
        raise HTTPException(status_code=404, detail=f"assessment '{assessment_id}' not found")
    return _to_read(repo, bank)
