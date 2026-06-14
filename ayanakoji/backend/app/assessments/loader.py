"""Seed the assessments database from the authored JSON banks (idempotent).

Each ``banks/<course>/<module>.json`` file holds two tests for one module. For a
file we create two ``AssessmentBank`` rows (``choices`` + ``llm``) plus their
question rows. Seeding is **clear-and-reload**: every call rebuilds the tables
from the on-disk JSON, so the DB is a deterministic projection of the content
(mirrors ``scripts/generate_work_iq.py`` discipline).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.assessments.models import (
    AssessmentBank,
    BankChoiceQuestion,
    BankLlmQuestion,
)
from app.assessments.validation import validate_bank


class BankValidationError(ValueError):
    """Raised when a bank file fails schema/semantic validation during a load."""


def banks_dir() -> Path:
    """Absolute path to ``ayanakoji/assessments/banks``."""
    # loader.py -> assessments -> app -> backend -> ayanakoji
    return Path(__file__).resolve().parents[3] / "assessments" / "banks"


def iter_bank_files(root: Path | None = None) -> list[Path]:
    """All bank JSON files, sorted for determinism."""
    base = root or banks_dir()
    return sorted(base.rglob("*.json"))


def _add_bank(session: Session, bank: dict[str, Any]) -> None:
    """Insert one module's two banks and their questions into the session."""
    course_id = str(bank["course_id"])
    module_id = str(bank["module_id"])
    title = str(bank["module_title"])

    choices_bank = AssessmentBank(
        course_id=course_id, module_id=module_id, kind="choices", title=f"{title} — Choices"
    )
    llm_bank = AssessmentBank(
        course_id=course_id, module_id=module_id, kind="llm", title=f"{title} — Explanation"
    )
    session.add(choices_bank)
    session.add(llm_bank)
    session.flush()  # assign bank ids before referencing them

    for q in bank["choices"]:
        session.add(
            BankChoiceQuestion(
                id=str(q["id"]),
                bank_id=choices_bank.id,
                course_id=course_id,
                module_id=module_id,
                prompt=str(q["prompt"]),
                kind=str(q["kind"]),
                choices=list(q["choices"]),
                correct_answers=list(q["correct_answers"]),
            )
        )
    for q in bank["llm"]:
        session.add(
            BankLlmQuestion(
                id=str(q["id"]),
                bank_id=llm_bank.id,
                course_id=course_id,
                module_id=module_id,
                prompt=str(q["prompt"]),
                reference_answer=str(q["reference_answer"]),
            )
        )


def _count(session: Session, model: type) -> int:
    return int(session.exec(select(func.count()).select_from(model)).one())


def _summary(session: Session, *, files: int) -> dict[str, int]:
    return {
        "files": files,
        "banks": _count(session, AssessmentBank),
        "choice_questions": _count(session, BankChoiceQuestion),
        "llm_questions": _count(session, BankLlmQuestion),
    }


def _load_banks(session: Session, banks: list[dict[str, Any]]) -> dict[str, int]:
    """Clear and reload pre-validated banks. Refuses to wipe the DB to empty.

    An empty ``banks`` list leaves the existing rows untouched — a failed/empty
    source must never silently delete a populated question bank.
    """
    if not banks:
        return _summary(session, files=0)

    session.exec(delete(BankChoiceQuestion))
    session.exec(delete(BankLlmQuestion))
    session.exec(delete(AssessmentBank))
    for bank in banks:
        _add_bank(session, bank)
    session.commit()
    return _summary(session, files=len(banks))


def seed_from_banks(session: Session, banks: list[dict[str, Any]]) -> dict[str, int]:
    """Validate, then clear-and-reload the given in-memory banks (e.g. pulled from Azure).

    Raises ``BankValidationError`` on the first invalid bank; nothing is written when
    any bank is invalid (validation happens before the clear-and-reload).
    """
    for bank in banks:
        errors = validate_bank(bank)
        if errors:
            raise BankValidationError(f"{bank.get('module_id', '?')}: " + "; ".join(errors))
    return _load_banks(session, banks)


def seed_database(session: Session, *, root: Path | None = None) -> dict[str, int]:
    """Clear and reload all banks from disk. Returns row counts. Raises on invalid bank."""
    banks: list[dict[str, Any]] = []
    for path in iter_bank_files(root):
        bank = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_bank(bank)
        if errors:
            raise BankValidationError(f"{path.name}: " + "; ".join(errors))
        banks.append(bank)
    return _load_banks(session, banks)
