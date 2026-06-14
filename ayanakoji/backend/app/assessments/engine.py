"""Engine + session lifecycle for the *separate* assessments database.

Mirrors ``app.db`` but owns its own module-global engine pointed at
``assessments_database_url`` so the question banks live in their own file and the
two databases never share a connection. ``init_db`` creates only the assessment
tables (``ASSESSMENT_TABLES``) so this engine never materializes course tables.
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
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def configure_engine(url: str, **kwargs: Any) -> Engine:
    """Build and install the assessments engine for ``url`` (replaces any existing)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, connect_args=_connect_args(url), **kwargs)
    return _engine


def get_engine() -> Engine:
    """Return the assessments engine, lazily built from settings on first use."""
    global _engine
    if _engine is None:
        url = get_settings().assessments_database_url
        _engine = create_engine(url, connect_args=_connect_args(url))
    return _engine


def reset_engine() -> None:
    """Dispose and clear the assessments engine (test teardown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    """Create *only* the assessment tables on the assessments engine."""
    from app.assessments.models import ASSESSMENT_TABLE_NAMES  # registers tables

    tables = [SQLModel.metadata.tables[name] for name in ASSESSMENT_TABLE_NAMES]
    SQLModel.metadata.create_all(get_engine(), tables=tables)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session bound to the assessments engine."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for code outside the request/Depends cycle (loaders, scripts)."""
    with Session(get_engine()) as session:
        yield session
