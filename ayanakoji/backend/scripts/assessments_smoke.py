"""Local smoke test for the assessment question banks.

Builds the assessments database from the on-disk JSON banks and runs a few
queries, printing counts and a sample. Uses a throwaway temp DB by default so it
never clobbers a real ``assessments.db``.

Run:  uv run python scripts/assessments_smoke.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.assessments import engine
from app.assessments.loader import banks_dir, iter_bank_files, seed_database
from app.assessments.models import AssessmentBank
from sqlmodel import Session, select


def main() -> int:
    files = iter_bank_files()
    print(f"== Assessment banks on disk: {len(files)} file(s) under {banks_dir()} ==")
    if not files:
        print("  (no bank JSON files yet — author some, then re-run)")

    tmp = Path(tempfile.mkdtemp(prefix="assessments-smoke-")) / "assessments.db"
    engine.configure_engine(f"sqlite:///{tmp}")
    engine.init_db()

    with Session(engine.get_engine()) as session:
        counts = seed_database(session)
        print(f"== Seeded {tmp.name} ==")
        for key, value in counts.items():
            print(f"  {key}: {value}")

        sample = session.exec(select(AssessmentBank).limit(3)).all()
        print("== Sample banks ==")
        for bank in sample:
            print(f"  {bank.id[:8]}  {bank.kind:8}  {bank.module_id}  {bank.title}")

    engine.reset_engine()
    # Healthy whether or not banks exist yet; counts must be internally consistent.
    expected_banks = counts["files"] * 2
    ok = counts["banks"] == expected_banks
    verdict = "OK" if ok else "MISMATCH"
    print(f"== {verdict}: banks == files*2 ({counts['banks']} == {expected_banks}) ==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
