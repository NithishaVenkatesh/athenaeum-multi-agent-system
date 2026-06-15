from __future__ import annotations

from app.db import ensure_course_columns, ensure_schema
from sqlalchemy import create_engine, text


def test_ensure_course_columns_adds_missing_columns_idempotently() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # A pre-existing 'course' table missing the new columns.
        conn.execute(
            text("CREATE TABLE course (id TEXT PRIMARY KEY, persona_id TEXT, chat_name TEXT)")
        )
    ensure_course_columns(engine)
    ensure_course_columns(engine)  # second run must be a no-op, not an error
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(course)"))}
    assert {"skill_source", "skill_scores", "pending_modules", "feedback_active"} <= cols


def test_ensure_schema_drops_removed_columns_and_adds_assessment_columns() -> None:
    """A pre-existing DB loses the now-derived status columns and gains the new ones."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE course (id TEXT PRIMARY KEY, persona_id TEXT, chat_name TEXT, "
                "status INTEGER NOT NULL DEFAULT 0)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE coursemodule (id TEXT PRIMARY KEY, course_id TEXT, module_id TEXT, "
                "completed BOOLEAN NOT NULL DEFAULT 0, completed_at DATETIME)"
            )
        )
        conn.execute(text("CREATE TABLE assessment (id TEXT PRIMARY KEY, type TEXT)"))

    ensure_schema(engine)
    ensure_schema(engine)  # idempotent

    with engine.begin() as conn:
        course_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(course)"))}
        module_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(coursemodule)"))}
        asmt_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(assessment)"))}

    assert "status" not in course_cols
    assert "completed" not in module_cols and "completed_at" not in module_cols
    assert {"attempts_to_pass", "passed_at"} <= asmt_cols
