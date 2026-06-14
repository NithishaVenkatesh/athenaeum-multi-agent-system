"""Seed the real ``assessments.db`` from the bank source (Azure Blob → local fallback).

The same routine the app runs at startup, exposed as a one-shot command for ops /
deploys / CI. With AZURE_STORAGE_ACCOUNT set it pulls the banks from Azure Blob;
otherwise it loads the in-repo JSON. Prints the source and row counts.

Run:  uv run --group foundry python scripts/assessments_seed.py   # blob
      uv run python scripts/assessments_seed.py                   # local only
"""

from __future__ import annotations

import sys

from app.assessments.engine import init_db
from app.assessments.seed import seed_on_startup


def main() -> int:
    init_db()  # ensure the schema exists before seeding
    summary = seed_on_startup()
    source = summary.get("source")
    print(f"== Seeded assessments.db from '{source}' ==")
    for key in ("banks", "choice_questions", "llm_questions"):
        print(f"  {key}: {summary.get(key, 0)}")
    return 0 if source != "none" and summary.get("choice_questions") else 1


if __name__ == "__main__":
    sys.exit(main())
