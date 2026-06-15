"""Manager Insights service: pure risk heuristics + insight assembly."""

from __future__ import annotations

from typing import Any

from app.manager.schemas import (
    CapacitySummary,
    PlatformEngagement,
    ReadinessBreakdown,
)
from app.manager.service import build_team_insights, risk_flags
from app.workiq.repository import get_repository

MANAGER_ID = "EMP-011"
TEAM_ID = "TEAM-A"


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


def test_build_team_insights_grounds_in_work_iq(session: Any) -> None:
    repo = get_repository()
    manager = repo.get_persona(MANAGER_ID)
    assert manager is not None
    insights = build_team_insights(repo, session, manager)
    assert insights is not None
    assert insights.team_id == TEAM_ID
    assert insights.manager_codename == "Polaris"
    # Source 1 readiness distribution (3 GO / 7 CONDITIONAL / 1 NOT_YET in the data).
    assert insights.readiness.total == insights.member_count
    assert insights.readiness.go + insights.readiness.conditional + insights.readiness.not_yet == (
        insights.readiness.total
    )
    # Source 2 is empty on a fresh DB — honest empty state, not a crash.
    assert insights.engagement.has_activity is False
    assert insights.engagement.members_active == 0
