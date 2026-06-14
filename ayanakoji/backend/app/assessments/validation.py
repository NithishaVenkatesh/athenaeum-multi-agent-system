"""Validate an authored question bank: JSON Schema + semantic cross-checks.

The JSON Schema (``ayanakoji/assessments/schema/bank.schema.json``) enforces
shape, counts, patterns, and option counts. It cannot express cross-field rules,
so this module adds them:

- ``mcq`` ⇒ exactly one correct answer; ``msq`` ⇒ two or more.
- every ``correct_answers`` entry appears verbatim in that question's ``choices``.
- question ids follow the ``<module_id>-c0N`` / ``-l0N`` convention and are unique.
- every nested ``module_id`` matches the bank's ``module_id``.

``validate_bank`` returns a list of human-readable error strings (empty == valid),
so callers (loader, CI, tests) can report every problem at once.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _schema_path() -> Path:
    # validation.py -> assessments -> app -> backend -> ayanakoji
    return Path(__file__).resolve().parents[3] / "assessments" / "schema" / "bank.schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _semantic_errors(bank: dict[str, Any]) -> list[str]:
    """Cross-field rules the JSON Schema can't express. Assumes shape already checked."""
    errors: list[str] = []
    module_id = bank.get("module_id")

    seen_ids: set[str] = set()
    for index, q in enumerate(bank.get("choices", [])):
        qid = q.get("id", f"choices[{index}]")
        expected_id = f"{module_id}-c{index + 1:02d}"
        if qid != expected_id:
            errors.append(f"choice {qid}: id should be {expected_id} (position {index + 1})")
        if qid in seen_ids:
            errors.append(f"duplicate question id {qid}")
        seen_ids.add(qid)
        if q.get("module_id") != module_id:
            errors.append(f"choice {qid}: module_id {q.get('module_id')} != bank {module_id}")

        choices = q.get("choices", [])
        correct = q.get("correct_answers", [])
        missing = [c for c in correct if c not in choices]
        if missing:
            errors.append(f"choice {qid}: correct answer(s) not in options: {missing}")
        kind = q.get("kind")
        if kind == "mcq" and len(correct) != 1:
            errors.append(f"choice {qid}: mcq must have exactly 1 correct, has {len(correct)}")
        if kind == "msq" and len(correct) < 2:
            errors.append(f"choice {qid}: msq must have >=2 correct, has {len(correct)}")

    for index, q in enumerate(bank.get("llm", [])):
        qid = q.get("id", f"llm[{index}]")
        expected_id = f"{module_id}-l{index + 1:02d}"
        if qid != expected_id:
            errors.append(f"llm {qid}: id should be {expected_id} (position {index + 1})")
        if qid in seen_ids:
            errors.append(f"duplicate question id {qid}")
        seen_ids.add(qid)
        if q.get("module_id") != module_id:
            errors.append(f"llm {qid}: module_id {q.get('module_id')} != bank {module_id}")

    return errors


def validate_bank(bank: dict[str, Any]) -> list[str]:
    """Return all validation errors for one bank dict (empty list == valid)."""
    schema_errors = sorted(_validator().iter_errors(bank), key=lambda e: list(e.path))
    if schema_errors:
        # Shape is wrong; report schema errors and skip semantic checks (they'd be noise).
        return [
            f"schema: {e.message} (at {'/'.join(str(p) for p in e.path) or '<root>'})"
            for e in schema_errors
        ]
    return _semantic_errors(bank)


def validate_bank_file(path: Path) -> list[str]:
    """Validate a bank JSON file on disk. A parse error is returned as an error string."""
    try:
        bank = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: cannot read/parse: {exc}"]
    return validate_bank(bank)
