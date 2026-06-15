"""Manager Insights assembly — pure functions over real platform activity.

Everything here is derived live from the team's actual course and assessment activity
in ``athenaeum.db`` and updates as learners progress; there are no static org metrics.

- **Readiness** is computed per learner from real course completion: GO once any course
  in their certification path (their vertical) is fully complete, CONDITIONAL once they
  have started but finished none, NOT_YET with no activity.
- **Certification-target progress** keeps the org's target list but fills ``ready_count``
  from that real readiness.
- **Platform engagement** aggregates real assessment attempts/passes.

Everything is aggregate-only by construction: the functions only ever return counts,
averages, and rates over a whole team, and cohorts below ``MIN_COHORT_SIZE`` are
suppressed so no row can surface a single individual.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.catalog.loader import get_catalog
from app.courses.models import Assessment, Course
from app.courses.repository import CourseRepository
from app.manager.schemas import (
    CertTargetProgress,
    CohortReadiness,
    PlatformEngagement,
    ReadinessBreakdown,
    RiskFlag,
    TeamInsights,
)
from app.workiq.models import Persona
from app.workiq.repository import WorkIQRepository

# A team pass rate below this (with enough attempts) is flagged as a risk.
LOW_PASS_RATE = 0.5
# Don't flag a pass-rate risk until enough graded attempts make the rate meaningful.
MIN_ATTEMPTS_FOR_PASS_RATE = 5
# A per-cohort breakdown (a seniority band, a cert-target group) is only shown when it
# has at least this many members. A row over a single member is not an aggregate: it is
# that one person's figure, attributable by the manager. Suppressing sub-threshold
# cohorts keeps every breakdown row aggregate-only (k-anonymity, k=2). The team-wide
# totals are unaffected — only the per-cohort slicing is withheld.
MIN_COHORT_SIZE = 2
# Stable display order for the seniority breakdown (unknown tiers append after).
_SENIORITY_ORDER = ("principal", "staff", "senior", "mid", "junior", "associate")

# Readiness levels, derived from real course completion.
_GO = "GO"
_CONDITIONAL = "CONDITIONAL"
_NOT_YET = "NOT_YET"


def _readiness_for_courses(repo: CourseRepository, session: Session, courses: list[Course]) -> str:
    """A single learner's readiness from their certification-path courses (real data).

    GO once any course is fully complete (every module's quiz and oral cleared);
    CONDITIONAL once there is any progress (a module cleared, or a graded attempt) but
    no finished course; NOT_YET with no activity. Mirrors the learner-side definition of
    completion (``CourseRepository.module_completed``) so the manager sees the same truth.
    """
    if not courses:
        return _NOT_YET
    started = False
    for course in courses:
        modules = repo.list_modules(course.id)
        done = repo.completed_module_ids(course.id)
        # Compare against DISTINCT module ids so a duplicate CourseModule row can't keep
        # a fully-completed course stuck at CONDITIONAL (done is a set; modules is a list).
        if modules and len(done) == len({m.module_id for m in modules}):
            return _GO  # a full course completed → ready
        if done:
            started = True  # partial progress; keep scanning for a completed course
    if started:
        return _CONDITIONAL
    # No module cleared yet, but any graded attempt still counts as "in progress".
    course_ids = [c.id for c in courses]
    attempted = session.exec(
        select(Assessment.id).where(
            col(Assessment.course_id).in_(course_ids),
            or_(col(Assessment.score).is_not(None), col(Assessment.passed_at).is_not(None)),
        )
    ).first()
    return _CONDITIONAL if attempted is not None else _NOT_YET


def _readiness_by_member(session: Session, members: list[Persona]) -> dict[str, str]:
    """Real readiness for each member, keyed by ``employee_id``.

    Restricts to each learner's certification path (courses whose catalog vertical matches
    the learner's vertical), joining ``Course.catalog_id`` to the catalog. Read-only.
    """
    repo = CourseRepository(session)
    vertical_of_course = {c.id: c.vertical for c in get_catalog()}
    statuses: dict[str, str] = {}
    for member in members:
        path_courses = [
            c
            for c in repo.list_for_persona(member.employee_id)
            if vertical_of_course.get(c.catalog_id or "") == member.vertical
        ]
        statuses[member.employee_id] = _readiness_for_courses(repo, session, path_courses)
    return statuses


def _readiness_of(members: list[Persona], statuses: dict[str, str]) -> ReadinessBreakdown:
    counts = Counter(statuses[m.employee_id] for m in members)
    go, cond, ny = counts.get(_GO, 0), counts.get(_CONDITIONAL, 0), counts.get(_NOT_YET, 0)
    return ReadinessBreakdown(go=go, conditional=cond, not_yet=ny, total=go + cond + ny)


def _by_seniority(members: list[Persona], statuses: dict[str, str]) -> list[CohortReadiness]:
    """Readiness grouped by seniority — the 'by role' rubric view, kept aggregate.

    A band with fewer than ``MIN_COHORT_SIZE`` members is suppressed: a one- (or near-)
    person band would expose that individual's readiness, which the manager could attribute.
    """
    groups: dict[str, list[Persona]] = {}
    for m in members:
        groups.setdefault(m.seniority, []).append(m)
    ordered = [s for s in _SENIORITY_ORDER if s in groups]
    ordered += [s for s in groups if s not in _SENIORITY_ORDER]
    out: list[CohortReadiness] = []
    for label in ordered:
        group = groups[label]
        if len(group) < MIN_COHORT_SIZE:
            continue  # too small to be an aggregate — would surface one person
        counts = Counter(statuses[m.employee_id] for m in group)
        out.append(
            CohortReadiness(
                label=label.capitalize(),
                go=counts.get(_GO, 0),
                conditional=counts.get(_CONDITIONAL, 0),
                not_yet=counts.get(_NOT_YET, 0),
                total=len(group),
            )
        )
    return out


def _cert_targets(
    repo: WorkIQRepository, team_id: str, members: list[Persona], statuses: dict[str, str]
) -> list[CertTargetProgress]:
    """Progress toward the team's cert targets — ``ready_count`` from real readiness."""
    targets = repo.get_cert_targets(team_id) or []
    out: list[CertTargetProgress] = []
    for target in targets:
        targeting = [m for m in members if m.learning.target_cert == target.cert]
        if len(targeting) < MIN_COHORT_SIZE:
            # Skip empty rows AND single-member cohorts: a "x/1 GO" row is one person's
            # readiness, not a team aggregate (k-anonymity, k=MIN_COHORT_SIZE).
            continue
        ready = sum(1 for m in targeting if statuses[m.employee_id] == _GO)
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


def platform_engagement(session: Session, member_employee_ids: list[str]) -> PlatformEngagement:
    """Aggregate the team's real assessment activity from ``athenaeum.db``.

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
    # A module is COMPLETED only when both its tests have passed (quiz "choices" AND
    # oral "llm") — the same definition the learner side uses. Counted per (course,
    # module), so it reflects total module completions across the team's real activity.
    passed_keys = {(a.course_id, a.module_id) for a in passed_rows if a.module_id is not None}
    passed_typed = {
        (a.course_id, a.module_id, a.type) for a in passed_rows if a.module_id is not None
    }
    modules_completed = sum(
        1
        for (course_id, module_id) in passed_keys
        if (course_id, module_id, "choices") in passed_typed
        and (course_id, module_id, "llm") in passed_typed
    )
    attempted = len(attempted_rows)
    passed = len(passed_rows)
    pass_rate = round(passed / attempted, 2) if attempted else None
    return PlatformEngagement(
        members_total=total,
        members_active=len(active),
        assessments_attempted=attempted,
        assessments_passed=passed,
        modules_with_a_pass=len(modules_passed),
        modules_completed=modules_completed,
        pass_rate=pass_rate,
        has_activity=attempted > 0,
    )


def risk_flags(
    readiness: ReadinessBreakdown,
    engagement: PlatformEngagement,
) -> list[RiskFlag]:
    """Aggregate, name-free risk flags from the real team signals (pure heuristics)."""
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
                    f"{readiness.not_yet} of {readiness.total} members have not completed any "
                    "course in their certification path yet."
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

    All figures are real and live: readiness is computed from the team's actual course
    completion and engagement from their real assessment attempts. The manager is
    excluded from learner aggregates (they are not a learner).
    """
    team = repo.get_team(manager.team_id)
    if team is None:
        return None
    members = [m for m in repo.list_personas(team_id=team.id) if not m.is_manager]

    statuses = _readiness_by_member(session, members)
    readiness = _readiness_of(members, statuses)
    engagement = platform_engagement(session, [m.employee_id for m in members])

    return TeamInsights(
        team_id=team.id,
        team_name=team.name,
        manager_codename=manager.codename,
        member_count=len(members),
        readiness=readiness,
        by_seniority=_by_seniority(members, statuses),
        cert_targets=_cert_targets(repo, team.id, members, statuses),
        engagement=engagement,
        risks=risk_flags(readiness, engagement),
    )
