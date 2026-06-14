"""SQLite persistence layer for the learner workspace.

Owns the SQLAlchemy engine and session lifecycle for courses, messages, and
assessments. SQLite by default (zero infra, fully offline); the schema is small
and owned here, so ``init_db`` runs ``create_all`` at startup instead of pulling
in a migration tool (YAGNI).

The engine is a module-global so both the FastAPI ``get_session`` dependency and
the streaming endpoint's standalone ``session_scope`` resolve the same database.
Tests call ``configure_engine`` to point at an isolated in-memory DB and
``reset_engine`` to tear it down.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def _connect_args(url: str) -> dict[str, Any]:
    # SQLite guards against cross-thread use by default; FastAPI runs sync routes
    # and the streaming generator on worker threads, so relax that for SQLite.
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def configure_engine(url: str, **kwargs: Any) -> Engine:
    """Build and install the process engine for ``url`` (replaces any existing)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, connect_args=_connect_args(url), **kwargs)
    return _engine


def get_engine() -> Engine:
    """Return the process engine, lazily building it from settings on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            connect_args=_connect_args(get_settings().database_url),
        )
    return _engine


def reset_engine() -> None:
    """Dispose and clear the engine (test teardown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    """Create the learner-workspace tables on the current engine.

    Scoped to ``COURSE_TABLES`` so the separate assessments database's tables
    (which share ``SQLModel.metadata``) are never created in ``athenaeum.db``.
    """
    from app.courses.models import COURSE_TABLE_NAMES

    tables = [SQLModel.metadata.tables[name] for name in COURSE_TABLE_NAMES]
    SQLModel.metadata.create_all(get_engine(), tables=tables)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session bound to the process engine, closed after use."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for code outside the request/Depends cycle (SSE generator)."""
    with Session(get_engine()) as session:
        yield session
