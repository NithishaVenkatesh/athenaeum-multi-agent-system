"""Session-scoped data access for courses, messages, and assessments.

Repository pattern (rules/common/patterns.md): the router and the streaming
generator depend on this typed surface, not on SQLModel queries. A repository
wraps one ``Session``; both the request-bound session and the SSE generator's
standalone session can drive it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, delete, select

from app.courses.models import Assessment, Course, CourseModule, make_message


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
        status: int | None = None,
    ) -> Course:
        """Apply a partial update. ``set_catalog`` distinguishes 'link to X' / 'unlink'
        from 'field not provided' (since ``catalog_id=None`` means unlink). ``status``
        is set only when provided (course-attempt encoding lives on ``Course.status``)."""
        if chat_name is not None:
            course.chat_name = chat_name
        if set_catalog:
            course.catalog_id = catalog_id
        if status is not None:
            course.status = status
        course.updated_at = datetime.now(UTC)
        self._session.add(course)
        self._session.commit()
        self._session.refresh(course)
        return course

    def save(self, course: Course) -> Course:
        """Persist in-place edits to a course (e.g. pace / schedule fields)."""
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

    # ── Study-plan modules (progress system of record) ───────────────────────

    def replace_modules(self, course_id: str, modules: list[dict[str, Any]]) -> None:
        """Replace a course's scheduled modules (idempotent — a rebuild overwrites).

        Preserves completion: a module already completed stays completed across a
        re-plan, since progress is the learner's and shouldn't be wiped by a reschedule.
        """
        done = {m.module_id: m.completed_at for m in self.list_modules(course_id) if m.completed}
        self._session.exec(delete(CourseModule).where(col(CourseModule.course_id) == course_id))
        for data in modules:
            mid = str(data["module_id"])
            self._session.add(
                CourseModule(
                    course_id=course_id,
                    module_id=mid,
                    title=str(data["title"]),
                    sequence=int(data["sequence"]),
                    estimated_minutes=int(data["estimated_minutes"]),
                    complete_before=str(data["complete_before"]),
                    scheduled=list(data.get("scheduled", [])),
                    completed=mid in done,
                    completed_at=done.get(mid),
                )
            )
        self._session.commit()

    def list_modules(self, course_id: str) -> list[CourseModule]:
        statement = (
            select(CourseModule)
            .where(CourseModule.course_id == course_id)
            .order_by(col(CourseModule.sequence))
        )
        return list(self._session.exec(statement).all())

    def get_module(self, course_id: str, module_id: str) -> CourseModule | None:
        statement = select(CourseModule).where(
            CourseModule.course_id == course_id, CourseModule.module_id == module_id
        )
        return self._session.exec(statement).first()

    def set_module_completed(self, module: CourseModule, *, completed: bool) -> CourseModule:
        module.completed = completed
        module.completed_at = datetime.now(UTC) if completed else None
        self._session.add(module)
        self._session.commit()
        self._session.refresh(module)
        return module
