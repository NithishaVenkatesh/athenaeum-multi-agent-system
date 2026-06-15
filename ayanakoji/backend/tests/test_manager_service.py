"""Manager Insights service: real-activity readiness + risk heuristics + assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.catalog.loader import get_catalog
from app.courses.models import Assessment, Course, CourseModule
from app.manager.schemas import PlatformEngagement, ReadinessBreakdown
from app.manager.service import build_team_insights, platform_engagement, risk_flags
from app.workiq.repository import WorkIQRepository, get_repository
from sqlmodel import Session

MANAGER_ID = "EMP-011"
TEAM_ID = "TEAM-A"
# TEAM-A has 11 personas in the synthetic data, one of which is the manager (Polaris).
TEAM_ENGINEER_COUNT = 10


def _engagement(*, active: int = 0, attempted: int = 0, passed: int = 0) -> PlatformEngagement:
    rate = round(passed / attempted, 2) if attempted else None
    return PlatformEngagement(
        members_total=11,
        members_active=active,
        assessments_attempted=attempted,
        assessments_passed=passed,
        modules_with_a_pass=passed,
        pass_rate=rate,
        has_activity=attempted > 0,
    )


def _complete_one_module(
    session: Session, repo: WorkIQRepository, employee_id: str, *, modules: int, completed: int
) -> None:
    """Seed a real course in the learner's certification path with ``modules`` modules,
    clearing both tests (quiz + oral) for the first ``completed`` of them."""
    persona = repo.get_persona(employee_id)
    assert persona is not None
    catalog_course = next(c for c in get_catalog() if c.vertical == persona.vertical)
    course = Course(persona_id=employee_id, chat_name="seed", catalog_id=catalog_course.id)
    session.add(course)
    session.commit()
    session.refresh(course)
    for i in range(1, modules + 1):
        module_id = f"{catalog_course.id}-m{i:02d}"
        session.add(
            CourseModule(
                course_id=course.id,
                module_id=module_id,
                title=f"Module {i}",
                sequence=i,
                estimated_minutes=60,
                complete_before="2026-12-31",
            )
        )
        if i <= completed:
            for kind in ("choices", "llm"):
                session.add(
                    Assessment(
                        course_id=course.id,
                        module_id=module_id,
                        type=kind,
                        attempt_number=1,
                        score=9.0,
                        passed=True,
                        attempts_to_pass=1,
                        passed_at=datetime.now(UTC),
                    )
                )
    session.commit()


# ── Risk heuristics (pure) ───────────────────────────────────────────────────


def test_exam_readiness_risk_is_medium_for_a_single_not_yet() -> None:
    readiness = ReadinessBreakdown(go=3, conditional=7, not_yet=1, total=11)
    flags = risk_flags(readiness, _engagement())
    exam = next(f for f in flags if f.area == "exam_readiness")
    assert exam.severity == "medium"
    assert "1 of 11" in exam.detail


def test_exam_readiness_risk_is_high_when_a_third_are_not_ready() -> None:
    readiness = ReadinessBreakdown(go=3, conditional=3, not_yet=5, total=11)
    flags = risk_flags(readiness, _engagement())
    exam = next(f for f in flags if f.area == "exam_readiness")
    assert exam.severity == "high"


def test_no_exam_risk_when_everyone_is_ready() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement())
    assert not any(f.area == "exam_readiness" for f in flags)


def test_engagement_risk_when_no_activity() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement(active=0, attempted=0))
    engagement = next(f for f in flags if f.area == "engagement")
    assert "0 of 11" in engagement.detail


def test_engagement_risk_when_pass_rate_is_low() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement(active=4, attempted=10, passed=3))
    engagement = next(f for f in flags if f.area == "engagement")
    assert "pass rate" in engagement.detail.lower()


def test_no_engagement_risk_with_healthy_pass_rate() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement(active=8, attempted=10, passed=9))
    assert not any(f.area == "engagement" for f in flags)


def test_low_pass_rate_not_flagged_below_min_sample() -> None:
    """A single failed attempt (n=1) is noise, not a team pass-rate risk."""
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement(active=1, attempted=1, passed=0))
    assert not any(f.area == "engagement" for f in flags)


def test_no_capacity_risk_area_exists() -> None:
    """Capacity is removed; the manager view carries no capacity risk anymore."""
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _engagement(active=8, attempted=10, passed=9))
    assert all(f.area != "capacity" for f in flags)


# ── Assembly + real readiness ─────────────────────────────────────────────────


def test_build_team_insights_is_aggregate_and_empty_on_a_fresh_db(session: Any) -> None:
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None
    insights = build_team_insights(repo, session, manager)
    assert insights is not None
    assert insights.team_id == TEAM_ID
    assert insights.manager_codename == "Polaris"
    # The manager is excluded from learner aggregates: engineers only.
    assert insights.member_count == TEAM_ENGINEER_COUNT
    # Fresh DB → no real activity → everyone NOT_YET (honest empty state, no static seed).
    assert insights.readiness.go == 0
    assert insights.readiness.not_yet == TEAM_ENGINEER_COUNT
    assert insights.readiness.total == insights.member_count
    # Seniority bands sum to the team and stay aggregate.
    assert insights.by_seniority
    assert sum(c.total for c in insights.by_seniority) == insights.member_count
    # No cert target shows anyone GO yet.
    assert all(t.ready_count == 0 for t in insights.cert_targets)
    assert insights.engagement.has_activity is False


def test_single_member_cohorts_are_suppressed(session: Any) -> None:
    """A cohort of one is not an aggregate. Cert-target rows below MIN_COHORT_SIZE (k=2)
    must never reach the manager view. AZ-204 and AI-102 each have one targeting engineer."""
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None
    insights = build_team_insights(repo, session, manager)
    assert insights is not None
    assert all(t.member_count >= 2 for t in insights.cert_targets)
    assert all(c.total >= 2 for c in insights.by_seniority)
    shown = {t.cert for t in insights.cert_targets}
    assert "AZ-204" not in shown
    assert "AI-102" not in shown
    assert "AZ-305" in shown


def test_readiness_reflects_real_course_completion(session: Any) -> None:
    """Completing a course flips a member to GO — the dashboard tracks real activity."""
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None

    before = build_team_insights(repo, session, manager)
    assert before is not None and before.readiness.go == 0

    _complete_one_module(session, repo, "EMP-001", modules=2, completed=2)

    after = build_team_insights(repo, session, manager)
    assert after is not None
    assert after.readiness.go == 1  # the engineer who finished a course is now GO
    assert after.readiness.not_yet == TEAM_ENGINEER_COUNT - 1
    assert after.readiness.total == before.readiness.total  # team size unchanged


def test_partial_progress_is_conditional_not_go(session: Any) -> None:
    """Started but not finished → CONDITIONAL, never GO."""
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None

    _complete_one_module(session, repo, "EMP-002", modules=3, completed=1)

    insights = build_team_insights(repo, session, manager)
    assert insights is not None
    assert insights.readiness.go == 0
    assert insights.readiness.conditional == 1


def test_platform_engagement_counts_latest_attempt_only(session: Session) -> None:
    """Retakes of the same module/type must not double-count (latest attempt only)."""
    course = Course(persona_id="EMP-001", chat_name="Vega — AZ-204")
    session.add(course)
    session.commit()
    session.refresh(course)
    session.add(
        Assessment(
            course_id=course.id,
            module_id="cb-c01-m01",
            type="choices",
            attempt_number=2,  # the surviving latest attempt after a retake
            score=9.0,
            passed=True,
            passed_at=datetime.now(UTC),
        )
    )
    session.commit()

    eng = platform_engagement(session, ["EMP-001"])
    assert eng.assessments_attempted == 1  # one module/type, not two attempts
    assert eng.assessments_passed == 1
    assert eng.members_active == 1
    assert eng.modules_with_a_pass == 1


def test_modules_completed_requires_both_quiz_and_oral(session: Session) -> None:
    """A module counts as completed only when BOTH its quiz and oral have passed."""
    course = Course(persona_id="EMP-001", chat_name="seed")
    session.add(course)
    session.commit()
    session.refresh(course)

    # Only the quiz (choices) passed so far → the module is NOT yet completed.
    session.add(
        Assessment(
            course_id=course.id,
            module_id="cb-c01-m01",
            type="choices",
            attempt_number=1,
            score=9.0,
            passed=True,
            passed_at=datetime.now(UTC),
        )
    )
    session.commit()
    assert platform_engagement(session, ["EMP-001"]).modules_completed == 0

    # Pass the oral (llm) too → now the module is completed.
    session.add(
        Assessment(
            course_id=course.id,
            module_id="cb-c01-m01",
            type="llm",
            attempt_number=1,
            score=8.0,
            passed=True,
            passed_at=datetime.now(UTC),
        )
    )
    session.commit()
    assert platform_engagement(session, ["EMP-001"]).modules_completed == 1
