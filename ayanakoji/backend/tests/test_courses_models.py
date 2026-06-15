"""Schema + persistence round-trips for the learner-workspace tables."""

from __future__ import annotations

from app.courses.models import (
    ASSESSMENT_TYPES,
    Assessment,
    ChoiceQuestion,
    Course,
    LlmQuestion,
    make_message,
)
from sqlmodel import Session, select


def test_course_defaults_round_trip(session: Session) -> None:
    course = Course(persona_id="EMP-001", chat_name="Intro to Azure Functions")
    session.add(course)
    session.commit()
    session.refresh(course)

    assert course.id  # uuid hex assigned
    assert course.catalog_id is None
    assert course.messages == []
    assert course.created_at is not None


def test_course_messages_persist_as_inline_array(session: Session) -> None:
    course = Course(persona_id="EMP-002", chat_name="Pipelines")
    session.add(course)
    session.commit()

    # Immutable update (reassign, never mutate in place) so SQLAlchemy tracks it.
    course.messages = [*course.messages, make_message("user", "What is CI/CD?")]
    course.messages = [*course.messages, make_message("assistant", "Continuous delivery...")]
    session.add(course)
    session.commit()

    stored = session.get(Course, course.id)
    assert stored is not None
    assert [m["role"] for m in stored.messages] == ["user", "assistant"]
    assert stored.messages[0]["content"] == "What is CI/CD?"
    assert "created_at" in stored.messages[0]


def test_assessment_success_record_round_trips(session: Session) -> None:
    """The permanent success record (attempts_to_pass) persists; defaults to None."""
    course = Course(persona_id="EMP-001", chat_name="Done")
    session.add(course)
    session.commit()

    fresh = Assessment(course_id=course.id, type="choices", attempt_number=1)
    passed = Assessment(course_id=course.id, type="choices", attempt_number=2, attempts_to_pass=2)
    session.add(fresh)
    session.add(passed)
    session.commit()

    assert session.get(Assessment, fresh.id).attempts_to_pass is None
    assert session.get(Assessment, passed.id).attempts_to_pass == 2  # passed on attempt 2


def test_assessment_practice_flag_and_question_records(session: Session) -> None:
    course = Course(persona_id="EMP-007", chat_name="ML")
    session.add(course)
    session.commit()

    practice = Assessment(course_id=course.id, type="choices", is_practice=True)
    evaluation = Assessment(course_id=course.id, type="llm", is_practice=False)
    session.add(practice)
    session.add(evaluation)
    session.commit()

    assert practice.type in ASSESSMENT_TYPES
    assert practice.is_practice is True
    assert evaluation.is_practice is False

    choice_q = ChoiceQuestion(
        assessment_id=practice.id,
        prompt="Which service runs serverless functions?",
        choices=["Azure Functions", "Blob Storage"],
        correct_answers=["Azure Functions"],
    )
    llm_q = LlmQuestion(
        assessment_id=evaluation.id,
        prompt="Explain retrieval-augmented generation.",
        messages=[make_message("assistant", "Explain retrieval-augmented generation.")],
    )
    session.add(choice_q)
    session.add(llm_q)
    session.commit()
    session.refresh(choice_q)
    session.refresh(llm_q)

    # Defaults: not yet submitted, correctness unknown, no learner answer yet.
    assert choice_q.submitted is False
    assert choice_q.is_correct is None
    assert choice_q.learner_choice is None
    assert llm_q.submitted is False
    assert llm_q.is_correct is None

    # Reverse relation: both assessments hang off the course.
    rows = session.exec(select(Assessment).where(Assessment.course_id == course.id)).all()
    assert {a.type for a in rows} == {"choices", "llm"}
