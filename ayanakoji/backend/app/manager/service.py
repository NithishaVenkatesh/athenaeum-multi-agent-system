"""Manager Insights assembly — pure functions over Work IQ + course activity.

Source 1 (Work IQ aggregates): readiness distribution, capacity, cert targets,
OKRs — computed over the team's *learners* (the manager is excluded from learner
aggregates). Source 2 (real platform activity): the latest assessment attempt per
module for the team's members, read-only over ``athenaeum.db``. No seed; an empty
result is reported honestly as "no activity yet".

Everything here is aggregate-only by construction: the functions only ever return
counts, averages, and rates over a whole team — never one person's figures.
"""

from __future__ import annotations

import math
from collections import Counter

from sqlmodel import Session, col, select

from app.courses.models import Assessment, Course
from app.manager.schemas import (
    CapacitySummary,
    CertTargetProgress,
    CohortReadiness,
    OkrProgress,
    PlatformEngagement,
    ReadinessBreakdown,
    RiskFlag,
    TeamInsights,
)
from app.workiq.models import Persona, Team
from app.workiq.repository import HEAVY_MEETING_THRESHOLD_HOURS, WorkIQRepository

# A team pass rate below this (with enough attempts) is flagged as a risk.
LOW_PASS_RATE = 0.5
# Don't flag a pass-rate risk until enough graded attempts make the rate meaningful.
MIN_ATTEMPTS_FOR_PASS_RATE = 5
# Stable display order for the seniority breakdown (unknown tiers append after).
_SENIORITY_ORDER = ("principal", "staff", "senior", "mid", "junior", "associate")


def _readiness_of(members: list[Persona]) -> ReadinessBreakdown:
    counts = Counter(m.learning.readiness_status for m in members)
    go, cond, ny = counts.get("GO", 0), counts.get("CONDITIONAL", 0), counts.get("NOT_YET", 0)
    return ReadinessBreakdown(go=go, conditional=cond, not_yet=ny, total=go + cond + ny)


def _capacity_of(team: Team, members: list[Persona]) -> CapacitySummary:
    n = max(len(members), 1)
    meeting = [m.work_signals.meeting_hours_per_week for m in members]
    focus = [m.work_signals.focus_hours_per_week for m in members]
    avg_meeting = round(sum(meeting) / n, 2)
    avg_focus = round(sum(focus) / n, 2)
    high = sum(h > HEAVY_MEETING_THRESHOLD_HOURS for h in meeting)
    return CapacitySummary(
        member_count=len(members),
        avg_meeting_hours_per_week=avg_meeting,
        avg_focus_hours_per_week=avg_focus,
        high_meeting_load_count=high,
        heavy_meeting_threshold_hours=HEAVY_MEETING_THRESHOLD_HOURS,
        # Constrained when meetings outweigh focus on average, or a third of the team
        # is over the heavy-meeting line (only meaningful with members present).
        constrained=bool(members) and (avg_meeting > avg_focus or high * 3 >= len(members)),
        target_study_hours_by_seniority=dict(team.capacity_policy.target_study_hours_by_seniority),
    )


def _by_seniority(members: list[Persona]) -> list[CohortReadiness]:
    """Readiness grouped by seniority — the 'by role' rubric view, kept aggregate."""
    groups: dict[str, list[Persona]] = {}
    for m in members:
        groups.setdefault(m.seniority, []).append(m)
    ordered = [s for s in _SENIORITY_ORDER if s in groups]
    ordered += [s for s in groups if s not in _SENIORITY_ORDER]
    out: list[CohortReadiness] = []
    for label in ordered:
        counts = Counter(m.learning.readiness_status for m in groups[label])
        out.append(
            CohortReadiness(
                label=label.capitalize(),
                go=counts.get("GO", 0),
                conditional=counts.get("CONDITIONAL", 0),
                not_yet=counts.get("NOT_YET", 0),
                total=len(groups[label]),
            )
        )
    return out


def _cert_targets(
    repo: WorkIQRepository, team: Team, members: list[Persona]
) -> list[CertTargetProgress]:
    targets = repo.get_cert_targets(team.id) or []
    out: list[CertTargetProgress] = []
    for target in targets:
        targeting = [m for m in members if m.learning.target_cert == target.cert]
        if not targeting:
            continue  # nobody on the team is working toward this cert — skip the empty row
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
    ``employee_id``). Reduces to the LATEST attempt per (course, module, type) —
    mirroring the app's latest-only model — so retakes / duplicate attempts are not
    double-counted. Read-only; returns an honest empty state with no activity, and
    never per-learner rows.
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
    # Keep only the latest attempt per (course, module, type).
    latest: dict[tuple[str, str | None, str], Assessment] = {}
    for a in assessments:
        key = (a.course_id, a.module_id, a.type)
        cur = latest.get(key)
        if cur is None or (a.attempt_number, a.created_at) > (cur.attempt_number, cur.created_at):
            latest[key] = a
    rows = list(latest.values())

    attempted_rows = [a for a in rows if a.score is not None or a.passed_at is not None]
    passed_rows = [a for a in rows if a.passed_at is not None]
    active = {
        course_to_persona[a.course_id] for a in attempted_rows if a.course_id in course_to_persona
    }
    modules_passed = {a.module_id for a in passed_rows if a.module_id is not None}
    attempted = len(attempted_rows)
    passed = len(passed_rows)
    pass_rate = round(passed / attempted, 2) if attempted else None
    return PlatformEngagement(
        members_total=total,
        members_active=len(active),
        assessments_attempted=attempted,
        assessments_passed=passed,
        modules_with_a_pass=len(modules_passed),
        pass_rate=pass_rate,
        has_activity=attempted > 0,
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
    elif (
        engagement.pass_rate is not None
        and engagement.pass_rate < LOW_PASS_RATE
        and engagement.assessments_attempted >= MIN_ATTEMPTS_FOR_PASS_RATE
    ):
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
    """Assemble the manager's team view. Returns None if the team is missing.

    Learner aggregates exclude the manager themselves (they are not a learner), so
    readiness, capacity, and engagement reflect the engineers on the team only.
    """
    team = repo.get_team(manager.team_id)
    if team is None:
        return None
    members = [m for m in repo.list_personas(team_id=team.id) if not m.is_manager]
    sprint = repo.get_sprint(team.id)

    readiness = _readiness_of(members)
    capacity = _capacity_of(team, members)
    engagement = platform_engagement(session, [m.employee_id for m in members])

    return TeamInsights(
        team_id=team.id,
        team_name=team.name,
        manager_codename=manager.codename,
        member_count=len(members),
        sprint_name=sprint.name if sprint else None,
        sprint_goal=sprint.goal if sprint else None,
        readiness=readiness,
        by_seniority=_by_seniority(members),
        capacity=capacity,
        cert_targets=_cert_targets(repo, team, members),
        okrs=_okrs(repo, team.id),
        engagement=engagement,
        risks=risk_flags(readiness, capacity, engagement),
    )
