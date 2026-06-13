"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app import db as db_module
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the deterministic offline LLM path so tests never reach live Azure."""
    monkeypatch.setenv("OFFLINE_LLM", "true")


@pytest.fixture
def db_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    """An isolated temp-file SQLite engine with the workspace schema created.

    A file (not ``:memory:``) so the request session and the SSE streaming
    session each get their own connection — mirroring production.
    """
    db_file = tmp_path_factory.mktemp("workspace-db") / "test.db"
    engine = db_module.configure_engine(f"sqlite:///{db_file}")
    db_module.init_db()
    try:
        yield engine
    finally:
        db_module.reset_engine()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    """A session bound to the test engine."""
    with Session(db_engine) as test_session:
        yield test_session


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    """A TestClient bound to a fresh app instance using the in-memory test DB."""
    with TestClient(create_app()) as test_client:
        yield test_client
