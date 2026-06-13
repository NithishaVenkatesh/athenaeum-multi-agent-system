"""Session-scoped data access for courses, messages, and assessments.

Repository pattern (rules/common/patterns.md): the router and the streaming
generator depend on this typed surface, not on SQLModel queries. A repository
wraps one ``Session``; both the request-bound session and the SSE generator's
standalone session can drive it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.courses.models import Assessment, Course, make_message


class CourseRepository:
    """Typed read/write access to one learner's workspace records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, persona_id: str, chat_name: str) -> Course:
        """Create a new course (chat). No message is stored here."""
        course = Course(persona_id=persona_id, chat_name=chat_name)
        self._session.add(course)
        self._session.commit()
        self._session.refresh(course)
        return course

    def get(self, course_id: str) -> Course | None:
        return self._session.get(Course, course_id)

    def list_for_persona(self, persona_id: str) -> list[Course]:
        """A persona's courses, most-recently-updated first (for the chooser)."""
        statement = (
            select(Course)
            .where(Course.persona_id == persona_id)
            .order_by(col(Course.updated_at).desc())
        )
        return list(self._session.exec(statement).all())

    def append_message(self, course: Course, *, role: str, content: str) -> Course:
        """Append one message immutably (reassign, never mutate) and bump updated_at."""
        course.messages = [*course.messages, make_message(role, content)]
        course.updated_at = datetime.now(UTC)
        self._session.add(course)
        self._session.commit()
        self._session.refresh(course)
        return course

    def update(
        self,
        course: Course,
        *,
        chat_name: str | None = None,
        catalog_id: str | None = None,
        set_catalog: bool = False,
    ) -> Course:
        """Apply a partial update. ``set_catalog`` distinguishes 'link to X' / 'unlink'
        from 'field not provided' (since ``catalog_id=None`` means unlink)."""
        if chat_name is not None:
            course.chat_name = chat_name
        if set_catalog:
            course.catalog_id = catalog_id
        course.updated_at = datetime.now(UTC)
        self._session.add(course)
        self._session.commit()
        self._session.refresh(course)
        return course

    def list_assessments(self, course_id: str) -> list[Assessment]:
        statement = select(Assessment).where(Assessment.course_id == course_id)
        return list(self._session.exec(statement).all())

    def assessment_ids(self, course_id: str) -> list[str]:
        return [a.id for a in self.list_assessments(course_id)]
