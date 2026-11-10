"""Tests for startup seeding from the in-repo JSON question banks.

The autouse ``_isolate_assessments_db`` fixture points the assessments engine at a
temp DB with the schema created, so ``seed_on_startup`` writes there.
"""

from __future__ import annotations

import pytest
from app.assessments import seed


def test_seed_on_startup_uses_local_banks() -> None:
    summary = seed.seed_on_startup()

    assert summary["source"] == "local"
    assert summary["choice_questions"] > 0  # real in-repo banks seeded


def test_seed_on_startup_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_session: object) -> dict[str, int]:
        raise RuntimeError("bad bank")

    monkeypatch.setattr(seed, "seed_database", _boom)

    summary = seed.seed_on_startup()

    assert summary == {"source": "none", "files": 0}
