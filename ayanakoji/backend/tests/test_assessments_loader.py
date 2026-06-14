"""Tests for the assessments loader (JSON banks -> assessments.db) and engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.assessments.loader import BankValidationError, seed_database, seed_from_banks
from app.assessments.models import AssessmentBank, BankChoiceQuestion, BankLlmQuestion
from sqlmodel import Session, select

from tests.test_assessments_validation import make_valid_bank


def _write_banks(root: Path, banks: list[dict]) -> None:
    for bank in banks:
        course_dir = root / bank["course_id"]
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / f"{bank['module_id']}.json").write_text(json.dumps(bank), encoding="utf-8")


def test_seed_loads_banks_and_questions(assessments_session: Session, tmp_path: Path) -> None:
    banks = [
        make_valid_bank("cb-c01", "cb-c01-m01"),
        make_valid_bank("cb-c01", "cb-c01-m02"),
    ]
    _write_banks(tmp_path, banks)

    counts = seed_database(assessments_session, root=tmp_path)

    assert counts == {
        "files": 2,
        "banks": 4,  # 2 modules x (choices + llm)
        "choice_questions": 20,  # 2 x 10
        "llm_questions": 6,  # 2 x 3
    }


def test_seed_is_idempotent(assessments_session: Session, tmp_path: Path) -> None:
    _write_banks(tmp_path, [make_valid_bank()])
    first = seed_database(assessments_session, root=tmp_path)
    second = seed_database(assessments_session, root=tmp_path)
    assert first == second  # reloading does not duplicate rows


def test_seeded_rows_carry_course_and_module(assessments_session: Session, tmp_path: Path) -> None:
    _write_banks(tmp_path, [make_valid_bank("cb-c01", "cb-c01-m01")])
    seed_database(assessments_session, root=tmp_path)

    choices_bank = assessments_session.exec(
        select(AssessmentBank).where(AssessmentBank.kind == "choices")
    ).one()
    assert choices_bank.module_id == "cb-c01-m01"
    assert choices_bank.course_id == "cb-c01"

    q = assessments_session.exec(
        select(BankChoiceQuestion).where(BankChoiceQuestion.id == "cb-c01-m01-c01")
    ).one()
    assert q.bank_id == choices_bank.id
    assert q.kind == "mcq"
    assert q.correct_answers == ["opt1a"]

    llm_q = assessments_session.exec(
        select(BankLlmQuestion).where(BankLlmQuestion.id == "cb-c01-m01-l01")
    ).one()
    assert llm_q.reference_answer.startswith("A correct reference answer")


def test_seed_rejects_invalid_bank(assessments_session: Session, tmp_path: Path) -> None:
    bad = make_valid_bank()
    bad["choices"][0]["correct_answers"] = ["not-an-option"]
    _write_banks(tmp_path, [bad])
    with pytest.raises(BankValidationError):
        seed_database(assessments_session, root=tmp_path)


def test_seed_from_banks_loads_in_memory(assessments_session: Session) -> None:
    """The Azure path seeds from in-memory dicts (no disk) the same as ``seed_database``."""
    banks = [make_valid_bank("cb-c01", "cb-c01-m01"), make_valid_bank("cb-c01", "cb-c01-m02")]

    counts = seed_from_banks(assessments_session, banks)

    assert counts == {"files": 2, "banks": 4, "choice_questions": 20, "llm_questions": 6}


def test_seed_from_banks_rejects_invalid_bank(assessments_session: Session) -> None:
    bad = make_valid_bank()
    bad["choices"][0]["correct_answers"] = ["not-an-option"]
    with pytest.raises(BankValidationError):
        seed_from_banks(assessments_session, [bad])


def test_seed_from_empty_banks_leaves_db_untouched(
    assessments_session: Session, tmp_path: Path
) -> None:
    """An empty source must not wipe an already-populated bank (failed-pull guard)."""
    _write_banks(tmp_path, [make_valid_bank("cb-c01", "cb-c01-m01")])
    seed_database(assessments_session, root=tmp_path)

    counts = seed_from_banks(assessments_session, [])

    assert counts["choice_questions"] == 10  # rows survived the empty reseed
    assert counts["files"] == 0


def test_assessments_db_is_separate_from_workspace(
    assessments_session: Session, session: Session
) -> None:
    """Course tables must not exist in assessments.db, and vice versa."""
    from sqlalchemy import inspect

    assess_tables = set(inspect(assessments_session.get_bind()).get_table_names())
    workspace_tables = set(inspect(session.get_bind()).get_table_names())

    assert "assessment_bank" in assess_tables
    assert "course" not in assess_tables
    assert "course" in workspace_tables
    assert "assessment_bank" not in workspace_tables
