"""AssessmentRepository.get_choice_question_by_id round-trips a bank question."""

from __future__ import annotations

from typing import Any

from app.assessments.repository import AssessmentRepository


def test_get_choice_question_by_id_round_trips(assessments_session: Any) -> None:
    from app.assessments.models import AssessmentBank, BankChoiceQuestion

    bank = AssessmentBank(course_id="cb-c01", module_id="cb-c01-m01", kind="choices", title="quiz")
    assessments_session.add(bank)
    assessments_session.commit()
    assessments_session.refresh(bank)
    assessments_session.add(
        BankChoiceQuestion(
            id="cb-c01-m01-c01",
            bank_id=bank.id,
            course_id="cb-c01",
            module_id="cb-c01-m01",
            prompt="q?",
            kind="mcq",
            choices=["A", "B"],
            correct_answers=["A"],
        )
    )
    assessments_session.commit()

    repo = AssessmentRepository(assessments_session)
    q = repo.get_choice_question_by_id("cb-c01-m01-c01")
    assert q is not None
    assert q.module_id == "cb-c01-m01"
    assert q.correct_answers == ["A"]
    assert repo.get_choice_question_by_id("nope") is None
