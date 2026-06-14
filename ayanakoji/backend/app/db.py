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

from sqlalchemy import Engine, event, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None

# Columns added to ``course`` after the initial release. SQLite's create_all never
# ALTERs an existing table, so a running dev DB needs them added in place.
_COURSE_ADDED_COLUMNS: dict[str, str] = {
    "skill_source": "TEXT",
    "skill_scores": "JSON",
    "pending_modules": "JSON",
}

# SQLite busy timeout (ms): how long a writer waits on a locked DB before erroring.
# Concurrent turns to *different* courses, plus the assessments DB, can briefly
# contend; WAL + this timeout turn transient "database is locked" into a short
# wait instead of a 500 (critique C4). Same-course turns are serialized in-process.
_SQLITE_BUSY_TIMEOUT_MS = 30_000


def _connect_args(url: str) -> dict[str, Any]:
    # SQLite guards against cross-thread use by default; FastAPI runs sync routes
    # and the streaming generator on worker threads, so relax that for SQLite.
    # ``timeout`` is the driver-level busy timeout (seconds).
    if url.startswith("sqlite"):
        return {"check_same_thread": False, "timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000}
    return {}


def _tune_sqlite(engine: Engine) -> Engine:
    """Enable WAL + a busy timeout on SQLite connections (no-op for other engines)."""
    if not engine.url.drivername.startswith("sqlite"):
        return engine

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:  # pragma: no cover - driver cb
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
        cursor.close()

    return engine


def configure_engine(url: str, **kwargs: Any) -> Engine:
    """Build and install the process engine for ``url`` (replaces any existing)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = _tune_sqlite(create_engine(url, connect_args=_connect_args(url), **kwargs))
    return _engine


def get_engine() -> Engine:
    """Return the process engine, lazily building it from settings on first use."""
    global _engine
    if _engine is None:
        _engine = _tune_sqlite(
            create_engine(
                get_settings().database_url,
                connect_args=_connect_args(get_settings().database_url),
            )
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

    Scoped to ``COURSE_TABLES`` (plus the notification/streak tables, which also
    live in the learner-workspace DB) so the separate assessments database's
    tables (which share ``SQLModel.metadata``) are never created in ``athenaeum.db``.
    """
    from app.courses.models import COURSE_TABLE_NAMES
    from app.notifications.models import NOTIFICATION_TABLE_NAMES

    names = (*COURSE_TABLE_NAMES, *NOTIFICATION_TABLE_NAMES)
    tables = [SQLModel.metadata.tables[name] for name in names]
    engine = get_engine()
    SQLModel.metadata.create_all(engine, tables=tables)
    ensure_course_columns(engine)


def ensure_course_columns(engine: Engine) -> None:
    """Add any missing additive columns to the ``course`` table (idempotent).

    SQLite-only and additive: ``create_all`` never ALTERs an existing table, so a
    dev DB that predates these columns gets them here instead of needing a full
    migration tool. Brand-new DBs already have the columns and this is a no-op.
    """
    if not engine.url.drivername.startswith("sqlite"):
        return
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(course)"))}
        for name, sql_type in _COURSE_ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE course ADD COLUMN {name} {sql_type}"))


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session bound to the process engine, closed after use."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for code outside the request/Depends cycle (SSE generator)."""
    with Session(get_engine()) as session:
        yield session
