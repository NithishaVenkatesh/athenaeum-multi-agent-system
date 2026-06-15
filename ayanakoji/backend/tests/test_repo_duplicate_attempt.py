"""Module completion must survive a duplicate in-progress attempt.

Regression for the live bug where passing the oral after the quiz left the module
stuck (next modules locked). A racing double-start (StrictMode double-mount, or the
404-recovery force-start firing while the first start was in flight) had left two
``llm`` rows sharing ``attempt_number`` — one passed, one orphaned in-progress. The
derived completion keyed off the *latest* attempt with a non-deterministic tie-break,
so it could resolve to the orphan and report the module incomplete forever.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.courses.models import Assessment
from app.courses.repository import CourseRepository
from sqlmodel import Session

COURSE = "course-x"
MODULE = "cb-c01-m01"


def _passed(session: Session, type: str, attempt: int, when: datetime) -> Assessment:
    a = Assessment(
        course_id=COURSE,
        module_id=MODULE,
        type=type,
        attempt_number=attempt,
        score=10.0,
        passed=True,
        completed_at=when,
        passed_at=when,
        attempts_to_pass=attempt,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def _orphan_in_progress(session: Session, type: str, attempt: int) -> Assessment:
    """An attempt that was started but never graded/submitted (the duplicate)."""
    a = Assessment(course_id=COURSE, module_id=MODULE, type=type, attempt_number=attempt)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def test_module_completes_despite_orphan_in_progress_oral(session: Session) -> None:
    repo = CourseRepository(session)
    _passed(session, "choices", attempt=2, when=datetime(2026, 6, 15, 3, 15, tzinfo=UTC))
    # The orphan is created FIRST (lower id), the real passed attempt SECOND — mirroring
    # the live data where the in-progress row predates the completed one at the same number.
    _orphan_in_progress(session, "llm", attempt=1)
    _passed(session, "llm", attempt=1, when=datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    assert repo.cleared(COURSE, MODULE, "llm") is True
    assert repo.module_completed(COURSE, MODULE) is True
    assert repo.module_completed_at(COURSE, MODULE) is not None


def test_latest_assessment_prefers_completed_over_orphan(session: Session) -> None:
    repo = CourseRepository(session)
    _orphan_in_progress(session, "llm", attempt=1)
    passed = _passed(session, "llm", attempt=1, when=datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    latest = repo.latest_assessment(COURSE, MODULE, "llm")
    assert latest is not None and latest.id == passed.id  # the real, passed attempt


def test_list_module_assessments_surfaces_the_passed_attempt(session: Session) -> None:
    repo = CourseRepository(session)
    _passed(session, "choices", attempt=1, when=datetime(2026, 6, 15, 3, 15, tzinfo=UTC))
    _orphan_in_progress(session, "llm", attempt=1)
    _passed(session, "llm", attempt=1, when=datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    by_type = {a.type: a for a in repo.list_module_assessments(COURSE, MODULE)}
    assert by_type["llm"].passed is True  # not the orphan (passed is None)


def test_retake_after_orphan_carries_the_pass_record_forward(session: Session) -> None:
    """A fresh retake must carry the permanent pass record from the passed attempt,
    not the orphan — otherwise the next attempt loses ``attempts_to_pass``."""
    repo = CourseRepository(session)
    _orphan_in_progress(session, "llm", attempt=1)
    _passed(session, "llm", attempt=1, when=datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    prior_count, attempts_to_pass, passed_at = repo.reset_for_new_attempt(COURSE, MODULE, "llm")
    assert attempts_to_pass == 1  # carried from the passed row, not the NULL orphan
    assert passed_at is not None
    assert prior_count == 1  # next attempt_number becomes 2 — no more duplicate at 1
