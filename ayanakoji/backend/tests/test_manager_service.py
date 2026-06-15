"""Manager Insights service: pure risk heuristics + insight assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.courses.models import Assessment, Course
from app.manager.schemas import (
    CapacitySummary,
    PlatformEngagement,
    ReadinessBreakdown,
)
from app.manager.service import build_team_insights, platform_engagement, risk_flags
from app.workiq.repository import get_repository
from sqlmodel import Session

MANAGER_ID = "EMP-011"
TEAM_ID = "TEAM-A"
# TEAM-A has 11 personas in the synthetic data, one of which is the manager (Polaris).
TEAM_ENGINEER_COUNT = 10


def _capacity(*, high: int = 0, members: int = 11) -> CapacitySummary:
    return CapacitySummary(
        member_count=members,
        avg_meeting_hours_per_week=12.0,
        avg_focus_hours_per_week=15.0,
        high_meeting_load_count=high,
        heavy_meeting_threshold_hours=20.0,
        constrained=high > 0,
        target_study_hours_by_seniority={"senior": 4, "junior": 6, "manager": 2},
    )


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


def test_exam_readiness_risk_is_medium_for_a_single_not_yet() -> None:
    readiness = ReadinessBreakdown(go=3, conditional=7, not_yet=1, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement())
    exam = next(f for f in flags if f.area == "exam_readiness")
    assert exam.severity == "medium"
    assert "1 of 11" in exam.detail


def test_exam_readiness_risk_is_high_when_a_third_are_not_ready() -> None:
    readiness = ReadinessBreakdown(go=3, conditional=3, not_yet=5, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement())
    exam = next(f for f in flags if f.area == "exam_readiness")
    assert exam.severity == "high"


def test_no_exam_risk_when_everyone_is_ready() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement())
    assert not any(f.area == "exam_readiness" for f in flags)


def test_capacity_risk_scales_with_heavy_meeting_load() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    assert not any(
        f.area == "capacity" for f in risk_flags(readiness, _capacity(high=0), _engagement())
    )
    medium = risk_flags(readiness, _capacity(high=2), _engagement())
    assert next(f for f in medium if f.area == "capacity").severity == "medium"
    high = risk_flags(readiness, _capacity(high=6), _engagement())
    assert next(f for f in high if f.area == "capacity").severity == "high"


def test_engagement_risk_when_no_activity() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement(active=0, attempted=0))
    engagement = next(f for f in flags if f.area == "engagement")
    assert "0 of 11" in engagement.detail


def test_engagement_risk_when_pass_rate_is_low() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement(active=4, attempted=10, passed=3))
    engagement = next(f for f in flags if f.area == "engagement")
    assert "pass rate" in engagement.detail.lower()


def test_no_engagement_risk_with_healthy_pass_rate() -> None:
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement(active=8, attempted=10, passed=9))
    assert not any(f.area == "engagement" for f in flags)


def test_low_pass_rate_not_flagged_below_min_sample() -> None:
    """A single failed attempt (n=1) is noise, not a team pass-rate risk."""
    readiness = ReadinessBreakdown(go=11, conditional=0, not_yet=0, total=11)
    flags = risk_flags(readiness, _capacity(), _engagement(active=1, attempted=1, passed=0))
    assert not any(f.area == "engagement" for f in flags)


def test_build_team_insights_grounds_in_work_iq(session: Any) -> None:
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None
    insights = build_team_insights(repo, session, manager)
    assert insights is not None
    assert insights.team_id == TEAM_ID
    assert insights.manager_codename == "Polaris"
    # The manager is excluded from learner aggregates: engineers only.
    assert insights.member_count == TEAM_ENGINEER_COUNT
    assert insights.readiness.total == insights.member_count
    assert insights.readiness.go + insights.readiness.conditional + insights.readiness.not_yet == (
        insights.readiness.total
    )
    # "By role" view (seniority bands) is present and sums to the team.
    assert insights.by_seniority
    assert sum(c.total for c in insights.by_seniority) == insights.member_count
    # Track record: only decided Pass/Fail counted (5 Pass / 2 Fail / 3 In-Progress).
    tr = insights.track_record
    assert tr.decided == 7
    assert tr.passed == 5
    assert tr.pass_rate is not None and 0.0 <= tr.pass_rate <= 1.0
    # Empty cert-target cohorts are never shown.
    assert all(t.member_count > 0 for t in insights.cert_targets)
    # Source 2 is empty on a fresh DB — honest empty state, not a crash.
    assert insights.engagement.has_activity is False
    assert insights.engagement.members_active == 0


def test_platform_engagement_counts_latest_attempt_only(session: Session) -> None:
    """Retakes of the same module/type must not double-count (latest attempt only)."""
    course = Course(persona_id="EMP-001", chat_name="Vega — AZ-204")
    session.add(course)
    session.commit()
    session.refresh(course)
    for attempt, score in ((1, 6.0), (2, 9.0)):
        session.add(
            Assessment(
                course_id=course.id,
                module_id="cb-c01-m01",
                type="choices",
                attempt_number=attempt,
                score=score,
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
