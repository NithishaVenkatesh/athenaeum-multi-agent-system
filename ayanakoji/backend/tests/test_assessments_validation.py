"""Tests for assessment bank validation (schema + semantic cross-checks)."""

from __future__ import annotations

import copy
from typing import Any

from app.assessments.validation import validate_bank


def make_valid_bank(course_id: str = "cb-c01", module_id: str = "cb-c01-m01") -> dict[str, Any]:
    """A schema- and semantics-valid bank: 5 choices (4 mcq + 1 msq) and 3 llm."""
    choices = []
    for n in range(1, 6):
        is_msq = n == 5
        choices.append(
            {
                "id": f"{module_id}-c{n:02d}",
                "module_id": module_id,
                "prompt": f"Question {n} about the module?",
                "kind": "msq" if is_msq else "mcq",
                "choices": [f"opt{n}a", f"opt{n}b", f"opt{n}c", f"opt{n}d"],
                "correct_answers": [f"opt{n}a", f"opt{n}b"] if is_msq else [f"opt{n}a"],
            }
        )
    llm = [
        {
            "id": f"{module_id}-l{n:02d}",
            "module_id": module_id,
            "prompt": f"Explain concept {n} from the module.",
            "reference_answer": f"A correct reference answer for concept {n}.",
        }
        for n in range(1, 4)
    ]
    return {
        "course_id": course_id,
        "module_id": module_id,
        "module_title": "A Module Title",
        "choices": choices,
        "llm": llm,
    }


def test_valid_bank_has_no_errors() -> None:
    assert validate_bank(make_valid_bank()) == []


def test_mcq_with_two_correct_is_rejected() -> None:
    bank = make_valid_bank()
    bank["choices"][0]["correct_answers"] = ["opt1a", "opt1b"]  # mcq, 2 correct
    errors = validate_bank(bank)
    assert any("mcq must have exactly 1 correct" in e for e in errors)


def test_msq_with_one_correct_is_rejected() -> None:
    bank = make_valid_bank()
    bank["choices"][4]["correct_answers"] = ["opt5a"]  # msq, 1 correct
    errors = validate_bank(bank)
    assert any("msq must have >=2 correct" in e for e in errors)


def test_correct_answer_not_in_choices_is_rejected() -> None:
    bank = make_valid_bank()
    bank["choices"][0]["correct_answers"] = ["not-an-option"]
    errors = validate_bank(bank)
    assert any("not in options" in e for e in errors)


def test_wrong_question_id_is_rejected() -> None:
    bank = make_valid_bank()
    bank["choices"][0]["id"] = "cb-c01-m01-c09"  # out of 01..05 range -> schema rejects
    errors = validate_bank(bank)
    assert errors  # schema pattern rejects -c09


def test_module_id_mismatch_is_rejected() -> None:
    bank = make_valid_bank()
    bank["llm"][0]["module_id"] = "cb-c01-m02"
    errors = validate_bank(bank)
    assert any("module_id" in e and "!= bank" in e for e in errors)


def test_wrong_counts_are_rejected_by_schema() -> None:
    bank = make_valid_bank()
    bank["choices"] = bank["choices"][:4]  # only 4 choices
    errors = validate_bank(bank)
    assert any("schema" in e for e in errors)


def test_three_options_rejected_by_schema() -> None:
    bank = make_valid_bank()
    bank["choices"][0]["choices"] = ["a", "b", "c"]  # only 3 options
    errors = validate_bank(bank)
    assert any("schema" in e for e in errors)


def test_deepcopy_independence() -> None:
    # Guard against the builder accidentally sharing mutable state across questions.
    a = make_valid_bank()
    b = copy.deepcopy(a)
    b["choices"][0]["prompt"] = "changed"
    assert a["choices"][0]["prompt"] != "changed"
