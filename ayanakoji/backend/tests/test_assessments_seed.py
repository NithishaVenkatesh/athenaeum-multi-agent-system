"""Tests for startup seeding (Azure Blob preferred, local disk fallback).

The autouse ``_isolate_assessments_db`` fixture points the assessments engine at a
temp DB with the schema created, so ``seed_on_startup`` writes there. No Azure SDK or
credentials are needed: the blob path is monkeypatched at ``pull_all_banks``.
"""

from __future__ import annotations

import pytest
from app.assessments.engine import session_scope
from app.assessments.loader import _count
from app.assessments.models import BankChoiceQuestion
from app.assessments.seed import seed_on_startup

from tests.test_assessments_validation import make_valid_bank


def _set_account(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Force the storage-account setting via env (overrides the repo .env value).

    ``None`` → empty string, which is falsy so seeding takes the local-disk path. A
    bare ``delenv`` would not work: pydantic falls back to the real value in ``.env``.
    """
    from app.config import get_settings

    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", value or "")
    get_settings.cache_clear()


def test_seed_on_startup_pulls_from_blob_when_account_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_account(monkeypatch, "acct")
    # ``pull_all_banks`` is imported lazily inside seed_on_startup; patch it on its module.
    from app.assessments import azure_blob

    monkeypatch.setattr(
        azure_blob, "pull_all_banks", lambda: [make_valid_bank("cb-c01", "cb-c01-m01")]
    )

    summary = seed_on_startup()

    assert summary["source"] == "azure_blob"
    assert summary["choice_questions"] == 10
    with session_scope() as session:
        assert _count(session, BankChoiceQuestion) == 10


def test_seed_on_startup_uses_disk_when_no_account(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_account(monkeypatch, None)

    summary = seed_on_startup()

    assert summary["source"] == "local"
    assert summary["choice_questions"] > 0  # real in-repo banks seeded


def test_seed_on_startup_falls_back_to_disk_when_blob_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_account(monkeypatch, "acct")
    from app.assessments import azure_blob

    def _boom() -> list:
        raise RuntimeError("blob unreachable")

    monkeypatch.setattr(azure_blob, "pull_all_banks", _boom)

    summary = seed_on_startup()

    assert summary["source"] == "local"
    assert summary["choice_questions"] > 0
