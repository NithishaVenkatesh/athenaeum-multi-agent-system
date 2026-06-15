"""Session-scoped data access for courses, messages, and assessments.

Repository pattern (rules/common/patterns.md): the router and the streaming
generator depend on this typed surface, not on SQLModel queries. A repository
wraps one ``Session``; both the request-bound session and the SSE generator's
standalone session can drive it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select

from app.courses.models import (
    Assessment,
    ChoiceQuestion,
    Course,
    CourseModule,
    LlmQuestion,
    make_message,
)

# Newest attempt first, with a deterministic tie-break. The latest-only model is meant
# to keep a single row per (course, module, type), but a racing double-start (a dev
# StrictMode double-mount, or the 404-recovery force-start firing while the first start
# is in flight) can leave two rows sharing the same ``attempt_number``. At a tie a
# *completed* attempt outranks an in-progress duplicate (``completed_at`` desc → NULLs
# last in SQLite), then ``id`` desc makes the result fully deterministic — so progress
# resolves to the real, passed attempt instead of an orphaned in-progress one.
_NEWEST_FIRST = (
    col(Assessment.attempt_number).desc(),
    col(Assessment.completed_at).desc(),
    col(Assessment.id).desc(),
)


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

    def append_message(
        self,
        course: Course,
        *,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> Course:
        """Append one message immutably (reassign, never mutate) and bump updated_at."""
        course.messages = [*course.messages, make_message(role, content, meta)]
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

        Progress is no longer stored on the module row: completion is derived from
        the assessments, which key on (course_id, module_id). So a re-plan can wipe
        and rewrite the schedule rows freely — a module's passed tests still resolve
        it as complete because they reference the stable catalog ``module_id``.
        """
        self._session.exec(delete(CourseModule).where(col(CourseModule.course_id) == course_id))
        for data in modules:
            self._session.add(
                CourseModule(
                    course_id=course_id,
                    module_id=str(data["module_id"]),
                    title=str(data["title"]),
                    sequence=int(data["sequence"]),
                    estimated_minutes=int(data["estimated_minutes"]),
                    complete_before=str(data["complete_before"]),
                    scheduled=list(data.get("scheduled", [])),
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

    # ── Derived module/course progress (from test results) ───────────────────
    #
    # Completion is no longer stored. A module is complete once both its tests have
    # been *cleared* (passed at least once, recorded permanently as attempts_to_pass).
    # All these key on the stable catalog ``module_id``, so a re-plan that rewrites
    # CourseModule rows never loses progress.

    def cleared(self, course_id: str, module_id: str, type: str) -> bool:
        """True if this module's test of ``type`` has ever been passed.

        Keys off the permanent success record (``attempts_to_pass``, set once and never
        cleared) across *all* stored attempts rather than only the latest. Normally the
        latest-only model keeps a single row per type, but a duplicate in-progress attempt
        (a racing double-start) must not be able to mask an earlier pass: completion is a
        permanent fact and never regresses, so any cleared attempt is enough.
        """
        statement = select(Assessment).where(
            Assessment.course_id == course_id,
            Assessment.module_id == module_id,
            Assessment.type == type,
            col(Assessment.attempts_to_pass).is_not(None),
        )
        return self._session.exec(statement).first() is not None

    def module_completed(self, course_id: str, module_id: str) -> bool:
        """A module is complete once both its quiz and oral have been cleared."""
        return self.cleared(course_id, module_id, "choices") and self.cleared(
            course_id, module_id, "llm"
        )

    def module_completed_at(self, course_id: str, module_id: str) -> datetime | None:
        """When the module was completed: the later of its two tests' first-pass times."""
        if not self.module_completed(course_id, module_id):
            return None
        times = [
            a.passed_at
            for type in ("choices", "llm")
            if (a := self.latest_assessment(course_id, module_id, type)) and a.passed_at
        ]
        return max(times) if times else None

    def completed_module_ids(self, course_id: str) -> set[str]:
        """The catalog module ids of this course's completed modules."""
        return {
            m.module_id
            for m in self.list_modules(course_id)
            if self.module_completed(course_id, m.module_id)
        }

    # ── Assessment session (latest attempt only + carried attempt count) ──────

    def create_assessment(
        self,
        *,
        course_id: str,
        module_id: str,
        course_module_id: str,
        type: str,
        attempt_number: int,
        attempts_to_pass: int | None = None,
        passed_at: datetime | None = None,
    ) -> Assessment:
        a = Assessment(
            course_id=course_id,
            module_id=module_id,
            course_module_id=course_module_id,
            type=type,
            attempt_number=attempt_number,
            attempts_to_pass=attempts_to_pass,
            passed_at=passed_at,
        )
        self._session.add(a)
        try:
            self._session.commit()
        except IntegrityError:
            # A concurrent start already created the (course, module, type) attempt and
            # the unique guard rejected this duplicate. Recover idempotently: hand back the
            # row that won the race instead of orphaning a second one (or 500-ing). Both
            # racing callers then drive the same session — exactly the latest-only intent.
            self._session.rollback()
            existing = self.latest_assessment(course_id, module_id, type)
            if existing is not None:
                return existing
            raise
        self._session.refresh(a)
        return a

    def reset_for_new_attempt(
        self, course_id: str, module_id: str, type: str
    ) -> tuple[int, int | None, datetime | None]:
        """Drop the prior attempt's records (only the latest is kept) and return the
        facts to carry forward: (prior attempt count, attempts_to_pass, passed_at).

        Keeping only the most recent attempt is the 'latest + count' model: each
        retake replaces the stored questions/answers, while the permanent success
        record (attempts_to_pass / passed_at) survives so completion never regresses.
        """
        statement = (
            select(Assessment)
            .where(
                Assessment.course_id == course_id,
                Assessment.module_id == module_id,
                Assessment.type == type,
            )
            .order_by(*_NEWEST_FIRST)
        )
        rows = list(self._session.exec(statement).all())
        prior = rows[0] if rows else None
        prior_count = prior.attempt_number if prior else 0
        attempts_to_pass = prior.attempts_to_pass if prior else None
        passed_at = prior.passed_at if prior else None
        ids = [a.id for a in rows]
        if ids:
            self._session.exec(
                delete(ChoiceQuestion).where(col(ChoiceQuestion.assessment_id).in_(ids))
            )
            self._session.exec(delete(LlmQuestion).where(col(LlmQuestion.assessment_id).in_(ids)))
            self._session.exec(delete(Assessment).where(col(Assessment.id).in_(ids)))
            self._session.commit()
        return prior_count, attempts_to_pass, passed_at

    def latest_assessment(self, course_id: str, module_id: str, type: str) -> Assessment | None:
        statement = (
            select(Assessment)
            .where(
                Assessment.course_id == course_id,
                Assessment.module_id == module_id,
                Assessment.type == type,
            )
            .order_by(*_NEWEST_FIRST)
        )
        return self._session.exec(statement).first()

    def latest_failed_assessment(
        self, course_id: str, module_id: str | None = None
    ) -> Assessment | None:
        """The most recently submitted FAILED assessment in a course (optionally one module).

        'Failed' is a submitted attempt (``completed_at`` set) with ``passed`` False;
        in-progress (``passed`` None) and passed attempts are skipped. Ordered by
        ``completed_at`` desc so a bare 'feedback on my failed test' resolves to the
        learner's latest miss. Course-scoped, so it only ever returns this chat's tests.
        """
        statement = select(Assessment).where(
            Assessment.course_id == course_id,
            col(Assessment.passed).is_(False),
            col(Assessment.completed_at).is_not(None),
        )
        if module_id is not None:
            statement = statement.where(Assessment.module_id == module_id)
        statement = statement.order_by(col(Assessment.completed_at).desc())
        return self._session.exec(statement).first()

    def get_assessment(self, assessment_id: str) -> Assessment | None:
        return self._session.get(Assessment, assessment_id)

    def list_module_assessments(self, course_id: str, module_id: str) -> list[Assessment]:
        """The latest attempt of each type for a module (≤ 2 rows: quiz + oral)."""
        statement = (
            select(Assessment)
            .where(Assessment.course_id == course_id, Assessment.module_id == module_id)
            .order_by(col(Assessment.type), *_NEWEST_FIRST)
        )
        latest_by_type: dict[str, Assessment] = {}
        for a in self._session.exec(statement).all():
            latest_by_type.setdefault(a.type, a)  # newest-first → first (best) per type wins
        return list(latest_by_type.values())

    def save_assessment(self, a: Assessment) -> Assessment:
        self._session.add(a)
        self._session.commit()
        self._session.refresh(a)
        return a

    # ── Choice questions ─────────────────────────────────────────────────────

    def add_choice_question(self, q: ChoiceQuestion) -> ChoiceQuestion:
        self._session.add(q)
        self._session.commit()
        self._session.refresh(q)
        return q

    def list_choice_questions(self, assessment_id: str) -> list[ChoiceQuestion]:
        statement = (
            select(ChoiceQuestion)
            .where(ChoiceQuestion.assessment_id == assessment_id)
            .order_by(col(ChoiceQuestion.sequence))
        )
        return list(self._session.exec(statement).all())

    def get_choice_question(self, question_id: str) -> ChoiceQuestion | None:
        return self._session.get(ChoiceQuestion, question_id)

    def save_choice_question(self, q: ChoiceQuestion) -> ChoiceQuestion:
        self._session.add(q)
        self._session.commit()
        self._session.refresh(q)
        return q

    # ── LLM questions ────────────────────────────────────────────────────────

    def add_llm_question(self, q: LlmQuestion) -> LlmQuestion:
        self._session.add(q)
        self._session.commit()
        self._session.refresh(q)
        return q

    def list_llm_questions(self, assessment_id: str) -> list[LlmQuestion]:
        statement = (
            select(LlmQuestion)
            .where(LlmQuestion.assessment_id == assessment_id)
            .order_by(col(LlmQuestion.id))
        )
        return list(self._session.exec(statement).all())

    def get_llm_question(self, question_id: str) -> LlmQuestion | None:
        return self._session.get(LlmQuestion, question_id)

    def save_llm_question(self, q: LlmQuestion) -> LlmQuestion:
        self._session.add(q)
        self._session.commit()
        self._session.refresh(q)
        return q
