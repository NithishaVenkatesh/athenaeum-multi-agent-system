from __future__ import annotations

from app.courses.models import Course


def test_course_has_skill_fields_with_safe_defaults() -> None:
    c = Course(persona_id="emp-1", chat_name="x")
    assert c.skill_source is None
    assert c.skill_scores == {}
    assert c.pending_modules == []
