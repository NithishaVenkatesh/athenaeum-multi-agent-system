"""SQLModel tables for the authored question banks (the ``assessments.db`` schema).

A ``AssessmentBank`` is one *test* for one module — there are two per module: a
``choices`` bank (5 MCQ/MSQ questions) and an ``llm`` bank (3 open-ended
questions). Questions carry their ``course_id`` and ``module_id`` directly so the
bank can be queried by module or by course without a join.

These tables are deliberately registered on the shared ``SQLModel.metadata`` but
created only on the assessments engine (see ``engine.init_db``), so they live in
``assessments.db`` and never in the learner workspace ``athenaeum.db``.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel

# The two kinds of bank / test per module.
BANK_KINDS = ("choices", "llm")
# Per-question kind for the choices test.
CHOICE_KINDS = ("mcq", "msq")


def _uuid() -> str:
    return uuid4().hex


class AssessmentBank(SQLModel, table=True):
    """One authored test for one module (``choices`` or ``llm``)."""

    __tablename__ = "assessment_bank"

    id: str = Field(default_factory=_uuid, primary_key=True)
    course_id: str = Field(index=True)
    module_id: str = Field(index=True)
    kind: str  # one of BANK_KINDS
    title: str


class BankChoiceQuestion(SQLModel, table=True):
    """A multiple-choice / multiple-select question within a ``choices`` bank."""

    __tablename__ = "bank_choice_question"

    id: str = Field(primary_key=True)  # authored id, e.g. "cb-c01-m01-c01"
    bank_id: str = Field(foreign_key="assessment_bank.id", index=True)
    course_id: str = Field(index=True)
    module_id: str = Field(index=True)
    prompt: str
    kind: str  # one of CHOICE_KINDS
    choices: list[str] = Field(default_factory=list, sa_type=JSON)
    correct_answers: list[str] = Field(default_factory=list, sa_type=JSON)


class BankLlmQuestion(SQLModel, table=True):
    """An open-ended question (with a reference answer) within an ``llm`` bank."""

    __tablename__ = "bank_llm_question"

    id: str = Field(primary_key=True)  # authored id, e.g. "cb-c01-m01-l01"
    bank_id: str = Field(foreign_key="assessment_bank.id", index=True)
    course_id: str = Field(index=True)
    module_id: str = Field(index=True)
    prompt: str
    reference_answer: str


# The exact table names that belong in assessments.db (used to scope create_all
# so the two databases stay cleanly separated). Looked up from metadata by name
# at create time to stay clean under mypy's view of SQLModel classes.
ASSESSMENT_TABLE_NAMES = (
    "assessment_bank",
    "bank_choice_question",
    "bank_llm_question",
)
