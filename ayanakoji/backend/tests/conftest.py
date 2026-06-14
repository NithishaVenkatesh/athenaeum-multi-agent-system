"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app import db as db_module
from app.assessments import engine as assessments_engine
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the deterministic offline LLM path so tests never reach live Azure.

    Also clears the cached settings so each test reads its own env (get_settings is
    process-cached in production, but per-test env overrides must still take effect).
    """
    from app.config import get_settings

    monkeypatch.setenv("OFFLINE_LLM", "true")
    # Keep startup hermetic: the app lifespan must not pull banks from Azure / disk.
    # Seeding is exercised directly in test_assessments_seed.py.
    monkeypatch.setenv("SEED_ASSESSMENTS_ON_STARTUP", "false")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_llm_breaker() -> None:
    """Clear the process-wide provider circuit breaker so failures from one test
    never leak into the next (critique M6 isolation)."""
    from app.agent.llm import reset_default_breaker

    reset_default_breaker()


@pytest.fixture(autouse=True)
def _isolate_assessments_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point the (separate) assessments engine at a temp file for every test.

    The app lifespan creates the assessments schema on startup, so without this
    the ``client`` fixture would write a stray ``assessments.db`` in the cwd.
    """
    db_file = tmp_path_factory.mktemp("assessments-db") / "assessments.db"
    assessments_engine.configure_engine(f"sqlite:///{db_file}")
    assessments_engine.init_db()
    try:
        yield
    finally:
        assessments_engine.reset_engine()


@pytest.fixture
def assessments_session(_isolate_assessments_db: None) -> Iterator[Session]:
    """A session bound to the isolated assessments engine."""
    with Session(assessments_engine.get_engine()) as test_session:
        yield test_session


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
