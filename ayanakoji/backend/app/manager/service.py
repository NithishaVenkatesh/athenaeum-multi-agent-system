"""Manager Insights assembly — pure functions over Work IQ + course activity.

Source 1 (Work IQ aggregates): readiness distribution, capacity, cert targets,
OKRs — read from the immutable Work IQ repository's aggregate-only surface.
Source 2 (real platform activity): assessment attempts / passes for the team's
members, read-only over ``athenaeum.db``. No seed; an empty result is reported
honestly as "no activity yet".

Everything here is aggregate-only by construction: the functions only ever return
counts, averages, and rates over a whole team — never one person's figures.
"""

from __future__ import annotations

import math

from sqlmodel import Session, col, select

from app.courses.models import Assessment, Course
from app.manager.schemas import (
    CapacitySummary,
    CertTargetProgress,
    OkrProgress,
    PlatformEngagement,
    ReadinessBreakdown,
    RiskFlag,
    TeamInsights,
)
from app.workiq.models import Persona, Team
from app.workiq.repository import HEAVY_MEETING_THRESHOLD_HOURS, WorkIQRepository

# A team pass rate below this (with some attempts on record) is flagged as a risk.
LOW_PASS_RATE = 0.5


def _readiness(repo: WorkIQRepository, team_id: str) -> ReadinessBreakdown:
    capacity = repo.team_capacity(team_id)
    dist = capacity.readiness_distribution if capacity else {}
    go = dist.get("GO", 0)
    conditional = dist.get("CONDITIONAL", 0)
    not_yet = dist.get("NOT_YET", 0)
    return ReadinessBreakdown(
        go=go, conditional=conditional, not_yet=not_yet, total=go + conditional + not_yet
    )


def _capacity(repo: WorkIQRepository, team: Team) -> CapacitySummary:
    cap = repo.team_capacity(team.id)
    member_count = cap.member_count if cap else len(team.member_employee_ids)
    avg_meeting = cap.avg_meeting_hours_per_week if cap else 0.0
    avg_focus = cap.avg_focus_hours_per_week if cap else 0.0
    high = cap.high_meeting_load_count if cap else 0
    return CapacitySummary(
        member_count=member_count,
        avg_meeting_hours_per_week=avg_meeting,
        avg_focus_hours_per_week=avg_focus,
        high_meeting_load_count=high,
        heavy_meeting_threshold_hours=HEAVY_MEETING_THRESHOLD_HOURS,
        # Constrained when meetings outweigh focus on average, or a third of the team
        # is over the heavy-meeting line.
        constrained=avg_meeting > avg_focus or high * 3 >= max(member_count, 1),
        target_study_hours_by_seniority=dict(team.capacity_policy.target_study_hours_by_seniority),
    )


def _cert_targets(
    repo: WorkIQRepository, team: Team, members: list[Persona]
) -> list[CertTargetProgress]:
    targets = repo.get_cert_targets(team.id) or []
    out: list[CertTargetProgress] = []
    for target in targets:
        targeting = [m for m in members if m.learning.target_cert == target.cert]
        ready = sum(1 for m in targeting if m.learning.readiness_status == "GO")
        out.append(
            CertTargetProgress(
                vertical=target.vertical,
                cert=target.cert,
                target_quarter=target.target_quarter,
                member_count=len(targeting),
                ready_count=ready,
            )
        )
    return out


def _okrs(repo: WorkIQRepository, team_id: str) -> list[OkrProgress]:
    return [
        OkrProgress(id=o.id, objective=o.objective, progress=o.progress)
        for o in (repo.get_okrs(team_id) or [])
    ]


def platform_engagement(session: Session, member_employee_ids: list[str]) -> PlatformEngagement:
    """Aggregate the team's real assessment activity from ``athenaeum.db`` (Source 2).

    Joins on ``Course.persona_id`` (the learner id chosen at login == the Work IQ
    ``employee_id``). Read-only; returns an honest empty state when there is no
    activity yet. Never returns per-learner rows — only team totals.
    """
    total = len(member_employee_ids)
    if not member_employee_ids:
        return PlatformEngagement(members_total=0, members_active=0, has_activity=False)

    course_rows = session.exec(
        select(Course.id, Course.persona_id).where(col(Course.persona_id).in_(member_employee_ids))
    ).all()
    course_to_persona: dict[str, str] = dict(course_rows)
    if not course_to_persona:
        return PlatformEngagement(members_total=total, members_active=0, has_activity=False)

    assessments = session.exec(
        select(Assessment).where(col(Assessment.course_id).in_(list(course_to_persona)))
    ).all()
    attempted = [a for a in assessments if a.score is not None]
    passed = [a for a in assessments if a.passed_at is not None]
    active = {course_to_persona[a.course_id] for a in attempted if a.course_id in course_to_persona}
    modules_passed = {a.module_id for a in passed if a.module_id is not None}
    pass_rate = round(len(passed) / len(attempted), 2) if attempted else None
    return PlatformEngagement(
        members_total=total,
        members_active=len(active),
        assessments_attempted=len(attempted),
        assessments_passed=len(passed),
        modules_with_a_pass=len(modules_passed),
        pass_rate=pass_rate,
        has_activity=bool(attempted),
    )


def risk_flags(
    readiness: ReadinessBreakdown,
    capacity: CapacitySummary,
    engagement: PlatformEngagement,
) -> list[RiskFlag]:
    """Aggregate, name-free risk flags from the team signals (pure heuristics)."""
    flags: list[RiskFlag] = []

    if readiness.not_yet > 0 and readiness.total > 0:
        # High when at least a third of the team is not yet ready.
        high = readiness.not_yet * 3 >= readiness.total
        flags.append(
            RiskFlag(
                area="exam_readiness",
                severity="high" if high else "medium",
                title="Exam-readiness risk",
                detail=(
                    f"{readiness.not_yet} of {readiness.total} members are NOT_YET ready for "
                    "their target certification."
                ),
            )
        )

    if capacity.high_meeting_load_count > 0:
        high = capacity.high_meeting_load_count * 2 >= max(capacity.member_count, 1)
        flags.append(
            RiskFlag(
                area="capacity",
                severity="high" if high else "medium",
                title="Capacity-constrained team",
                detail=(
                    f"{capacity.high_meeting_load_count} of {capacity.member_count} members are "
                    f"above {math.floor(capacity.heavy_meeting_threshold_hours)}h of meetings per "
                    "week, which squeezes study time."
                ),
            )
        )

    if not engagement.has_activity:
        flags.append(
            RiskFlag(
                area="engagement",
                severity="medium",
                title="No platform engagement yet",
                detail=(
                    f"0 of {engagement.members_total} members have started any assessment in the "
                    "platform yet."
                ),
            )
        )
    elif engagement.pass_rate is not None and engagement.pass_rate < LOW_PASS_RATE:
        flags.append(
            RiskFlag(
                area="engagement",
                severity="medium",
                title="Low assessment pass rate",
                detail=(
                    f"Team pass rate is {engagement.pass_rate:.0%} across "
                    f"{engagement.assessments_attempted} graded attempts."
                ),
            )
        )

    return flags


def build_team_insights(
    repo: WorkIQRepository, session: Session, manager: Persona
) -> TeamInsights | None:
    """Assemble the manager's team view. Returns None if the team is missing."""
    team = repo.get_team(manager.team_id)
    if team is None:
        return None
    members = repo.list_personas(team_id=team.id)
    sprint = repo.get_sprint(team.id)

    readiness = _readiness(repo, team.id)
    capacity = _capacity(repo, team)
    engagement = platform_engagement(session, list(team.member_employee_ids))

    return TeamInsights(
        team_id=team.id,
        team_name=team.name,
        manager_codename=manager.codename,
        member_count=len(members),
        sprint_name=sprint.name if sprint else None,
        sprint_goal=sprint.goal if sprint else None,
        readiness=readiness,
        capacity=capacity,
        cert_targets=_cert_targets(repo, team, members),
        okrs=_okrs(repo, team.id),
        engagement=engagement,
        risks=risk_flags(readiness, capacity, engagement),
    )
