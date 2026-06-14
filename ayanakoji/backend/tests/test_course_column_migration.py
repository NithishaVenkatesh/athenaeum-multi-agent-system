from __future__ import annotations

from app.db import ensure_course_columns
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
    assert {"skill_source", "skill_scores", "pending_modules"} <= cols
