"""Session-scoped read access to the assessment question banks.

Repository pattern (rules/common/patterns.md): the router depends on this typed
surface, not on SQLModel queries. Read-only — the banks are authored content,
seeded by the loader, never mutated through the API.
"""

from __future__ import annotations

from sqlmodel import Session, col, select

from app.assessments.models import AssessmentBank, BankChoiceQuestion, BankLlmQuestion


class AssessmentRepository:
    """Typed read access to one assessments database session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_bank(self, assessment_id: str) -> AssessmentBank | None:
        return self._session.get(AssessmentBank, assessment_id)

    def choice_questions(self, bank_id: str) -> list[BankChoiceQuestion]:
        statement = (
            select(BankChoiceQuestion)
            .where(BankChoiceQuestion.bank_id == bank_id)
            .order_by(col(BankChoiceQuestion.id))
        )
        return list(self._session.exec(statement).all())

    def llm_questions(self, bank_id: str) -> list[BankLlmQuestion]:
        statement = (
            select(BankLlmQuestion)
            .where(BankLlmQuestion.bank_id == bank_id)
            .order_by(col(BankLlmQuestion.id))
        )
        return list(self._session.exec(statement).all())

    def assessment_ids_for_module(self, module_id: str) -> list[str]:
        """Bank ids for a module (the two tests: choices + llm), ordered by kind."""
        statement = (
            select(AssessmentBank.id)
            .where(AssessmentBank.module_id == module_id)
            .order_by(col(AssessmentBank.kind))
        )
        return list(self._session.exec(statement).all())

    def assessment_ids_for_course(self, course_id: str) -> list[str]:
        """All bank ids for a course, ordered by module then kind."""
        statement = (
            select(AssessmentBank.id)
            .where(AssessmentBank.course_id == course_id)
            .order_by(col(AssessmentBank.module_id), col(AssessmentBank.kind))
        )
        return list(self._session.exec(statement).all())
