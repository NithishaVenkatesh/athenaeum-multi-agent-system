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


def seed_database(session: Session, *, root: Path | None = None) -> dict[str, int]:
    """Clear and reload all banks from disk. Returns row counts. Raises on invalid bank."""
    files = iter_bank_files(root)
    banks: list[dict[str, Any]] = []
    for path in files:
        bank = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_bank(bank)
        if errors:
            raise BankValidationError(f"{path.name}: " + "; ".join(errors))
        banks.append(bank)

    session.exec(delete(BankChoiceQuestion))
    session.exec(delete(BankLlmQuestion))
    session.exec(delete(AssessmentBank))
    for bank in banks:
        _add_bank(session, bank)
    session.commit()

    def _count(model: type) -> int:
        return int(session.exec(select(func.count()).select_from(model)).one())

    return {
        "files": len(files),
        "banks": _count(AssessmentBank),
        "choice_questions": _count(BankChoiceQuestion),
        "llm_questions": _count(BankLlmQuestion),
    }
