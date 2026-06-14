"""Validate every authored assessment bank (schema + semantic rules). CI gate.

Walks ``ayanakoji/assessments/banks`` and validates each JSON file with the same
validator the loader uses (schema + cross-field checks: mcq/msq correctness,
answers-in-choices, id convention, module_id consistency). Exits non-zero if any
bank is invalid, so CI fails loudly on a malformed bank.

Run:  uv run python scripts/validate_banks.py
"""

from __future__ import annotations

import sys

from app.assessments.loader import banks_dir, iter_bank_files
from app.assessments.validation import validate_bank_file


def main() -> int:
    files = iter_bank_files()
    base = banks_dir()
    print(f"Validating {len(files)} bank file(s) under {base} …")
    failures: list[str] = []
    for path in files:
        errors = validate_bank_file(path)
        if errors:
            rel = path.relative_to(base)
            failures.append(f"{rel}: " + "; ".join(errors))

    if failures:
        print(f"\nFAILED — {len(failures)} invalid bank(s):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print(f"OK — all {len(files)} banks valid (10 choices + 3 llm each, keys consistent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
