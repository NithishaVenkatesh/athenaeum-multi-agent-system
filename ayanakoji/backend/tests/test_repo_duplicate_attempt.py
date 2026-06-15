"""The latest-only invariant is enforced at the DB level, race-proof.

Regression for the live bug where passing the oral after the quiz left the module
stuck (next modules locked). A racing double-start (StrictMode double-mount, or a
404-recovery force-start firing while the first start was in flight) had inserted two
``llm`` rows for one (course, module, type) — one passed, one orphaned in-progress —
and the derived completion could resolve to the orphan and report the module
incomplete forever.

The fix is a unique guard on (course_id, module_id, type): a second concurrent start
is rejected instead of orphaning a duplicate, and ``create_session_atomic`` recovers by
handing back the row that won the race (along with its question set).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.courses.models import Assessment
from app.courses.repository import CourseRepository
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

COURSE = "course-x"
MODULE = "cb-c01-m01"


def _pass(repo: CourseRepository, session: Session, type: str, when: datetime) -> Assessment:
    """Create and pass a fresh attempt of ``type`` (single row per type — no duplicates)."""
    a, _, _ = repo.create_session_atomic(
        Assessment(
            course_id=COURSE,
            module_id=MODULE,
            course_module_id="cm-1",
            type=type,
            attempt_number=1,
        ),
        [],
        [],
    )
    a.score = 10.0
    a.passed = True
    a.completed_at = when
    a.passed_at = when
    a.attempts_to_pass = 1
    session.add(a)
    session.commit()
    return a


def test_module_completes_on_quiz_and_oral_pass(session: Session) -> None:
    repo = CourseRepository(session)
    _pass(repo, session, "choices", datetime(2026, 6, 15, 3, 15, tzinfo=UTC))
    _pass(repo, session, "llm", datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    assert repo.cleared(COURSE, MODULE, "llm") is True
    assert repo.module_completed(COURSE, MODULE) is True
    assert repo.module_completed_at(COURSE, MODULE) is not None


def test_unique_guard_rejects_a_duplicate_attempt_row(session: Session) -> None:
    """A raw second row for the same (course, module, type) must be rejected."""
    session.add(Assessment(course_id=COURSE, module_id=MODULE, type="llm", attempt_number=1))
    session.commit()
    session.add(Assessment(course_id=COURSE, module_id=MODULE, type="llm", attempt_number=1))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_create_session_atomic_is_idempotent_under_a_racing_start(session: Session) -> None:
    """Two starts for the same (course, module, type) resolve to ONE row, not an orphan."""
    repo = CourseRepository(session)
    first, _, _ = repo.create_session_atomic(
        Assessment(
            course_id=COURSE,
            module_id=MODULE,
            course_module_id="cm-1",
            type="llm",
            attempt_number=1,
        ),
        [],
        [],
    )
    second, _, _ = repo.create_session_atomic(
        Assessment(
            course_id=COURSE,
            module_id=MODULE,
            course_module_id="cm-1",
            type="llm",
            attempt_number=1,
        ),
        [],
        [],
    )

    assert second.id == first.id  # the racing duplicate got the winner, not a new orphan
    llm_rows = [a for a in session.exec(select(Assessment)).all() if a.type == "llm"]
    assert len(llm_rows) == 1


def test_create_session_atomic_reraises_when_no_winner_can_be_found(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A unique violation with no recoverable winner row fails loud, not silently.

    The recovery path only makes sense when the racing winner's row exists. If an integrity
    error fires but no surviving (course, module, type) row can be found, the error must
    propagate rather than be swallowed into a wrong result."""
    repo = CourseRepository(session)
    repo.create_session_atomic(
        Assessment(
            course_id=COURSE,
            module_id=MODULE,
            course_module_id="cm-1",
            type="llm",
            attempt_number=1,
        ),
        [],
        [],
    )
    # Force the recovery lookup to find nothing, so the duplicate's IntegrityError has no
    # winner to hand back and must re-raise.
    monkeypatch.setattr(CourseRepository, "latest_assessment", lambda *a, **k: None)
    with pytest.raises(IntegrityError):
        repo.create_session_atomic(
            Assessment(
                course_id=COURSE,
                module_id=MODULE,
                course_module_id="cm-1",
                type="llm",
                attempt_number=1,
            ),
            [],
            [],
        )
    session.rollback()


def test_retake_replaces_the_row_and_carries_the_pass_record(session: Session) -> None:
    """A forced retake deletes the prior row and carries attempts_to_pass forward —
    so it stays a single row per type and completion never regresses."""
    repo = CourseRepository(session)
    _pass(repo, session, "llm", datetime(2026, 6, 15, 3, 16, tzinfo=UTC))

    prior_count, attempts_to_pass, passed_at = repo.reset_for_new_attempt(COURSE, MODULE, "llm")
    assert (prior_count, attempts_to_pass) == (1, 1)  # carried forward from the passed row
    assert passed_at is not None
    # The retake row can now be created without tripping the unique guard (prior deleted).
    retake, _, _ = repo.create_session_atomic(
        Assessment(
            course_id=COURSE,
            module_id=MODULE,
            course_module_id="cm-1",
            type="llm",
            attempt_number=prior_count + 1,
            attempts_to_pass=attempts_to_pass,
            passed_at=passed_at,
        ),
        [],
        [],
    )
    assert retake.attempt_number == 2
    assert repo.cleared(COURSE, MODULE, "llm") is True  # never regresses
