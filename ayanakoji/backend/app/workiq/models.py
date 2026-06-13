"""Typed contracts for the synthetic Work IQ service.

These mirror the shape of ``app/data/work_iq.json`` exactly and double as the
validation gate for that data source (the offline test suite validates the
committed JSON against these models). Literals encode the synthetic-data
contract (synthetic-data.md) so a drifted value fails loud at load time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Seniority = Literal["senior", "junior", "manager"]
LearningSlot = Literal["Morning", "Afternoon"]
ExamOutcome = Literal["Pass", "Fail", "In Progress"]
ReadinessStatus = Literal["GO", "CONDITIONAL", "NOT_YET"]
CollaborationLoad = Literal["low", "medium", "high", "very-high"]
Weekday = Literal["mon", "tue", "wed", "thu", "fri"]
BlockMeter = Literal["meeting", "focus", "collab", "neutral"]
BlockCategory = Literal[
    "standup",
    "meeting",
    "one_on_one",
    "ceremony",
    "interview",
    "focus",
    "learning",
    "pairing",
    "code_review",
    "deploy",
    "incident",
    "on_call",
    "lunch",
    "admin",
]
WorkMode = Literal["office", "remote", "hybrid"]
Modality = Literal["hands_on_lab", "video", "reading", "instructor_led"]
Pace = Literal["intensive", "steady", "light"]
AfterHoursLoad = Literal["none", "low", "moderate", "high"]
LevelCode = Literal["L3", "L4", "L5", "L6", "L7"]
EmploymentType = Literal["full_time", "contractor"]


class _Model(BaseModel):
    """Base: forbid unknown fields so JSON drift is caught at validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CalendarBlock(_Model):
    """A single timed block in a persona's day."""

    start: str
    end: str
    category: BlockCategory
    meter: BlockMeter
    duration_hours: float
    title: str
    collaborative: bool


class TimeWindow(_Model):
    """A simple HH:MM start/end window."""

    start: str
    end: str


class DaySummary(_Model):
    """Derived per-day rollup of a schedule (Work IQ workload-insight signal)."""

    meeting_hours: float
    focus_hours: float
    learning_hours: float
    collab_hours: float
    block_count: int
    longest_focus_block_minutes: int
    fragmentation_score: float
    free_capacity_hours: float


class DaySchedule(_Model):
    day: Weekday
    date: str
    blocks: list[CalendarBlock]
    summary: DaySummary


class WeekSchedule(_Model):
    week_id: str
    days: list[DaySchedule]


class WorkSignals(_Model):
    """Work IQ Dataset 2 surface — derived from the schedule."""

    employee_id: str
    meeting_hours_per_week: float
    focus_hours_per_week: float
    preferred_learning_slot: LearningSlot
    collaboration_load: CollaborationLoad


class LearnerProfile(_Model):
    """Learner-performance (Dataset 1) surface for a persona."""

    learner_id: str
    role: str
    certification: str
    practice_score_avg: int
    hours_studied: int
    exam_outcome: ExamOutcome
    target_cert: str
    recommended_hours: int
    readiness_status: ReadinessStatus


class LearningPreferences(_Model):
    """Bundle A — how a learner wants to study (drives study-slot scheduling)."""

    preferred_study_hours_per_week: int
    preferred_session_minutes: int
    preferred_study_days: list[Weekday]
    study_window: TimeWindow
    preferred_modality: Modality
    pace: Pace
    reminder_opt_in: bool


class OnCall(_Model):
    is_on_call: bool
    dates: list[str]


class WorkContext(_Model):
    """Bundle B — availability and workload shape (Work IQ workload insights)."""

    work_mode: WorkMode
    working_hours: TimeWindow
    working_days: list[Weekday]
    focus_windows: list[TimeWindow]
    on_call: OnCall
    pto_days: list[str]
    after_hours_load: AfterHoursLoad
    context_switch_score: float
    longest_focus_block_minutes: int
    response_latency_minutes: int


class Profile(_Model):
    """Bundle E — synthetic HR identity (fabricated; no PII)."""

    start_date: str
    tenure_months: int
    level_code: LevelCode
    years_experience: int
    location: str
    employment_type: EmploymentType
    languages: list[str]


class Persona(_Model):
    """A full org member: identity, role, work signals, learner profile, schedule."""

    employee_id: str
    learner_id: str
    codename: str
    team_id: str
    vertical: str
    seniority: Seniority
    role_title: str
    certification: str
    is_manager: bool
    manager_employee_id: str | None
    reports: list[str]
    timezone: str
    preferred_learning_slot: LearningSlot
    profile: Profile
    learning_preferences: LearningPreferences
    work_context: WorkContext
    work_signals: WorkSignals
    learning: LearnerProfile
    schedule: WeekSchedule


class Vertical(_Model):
    id: str
    title: str
    primary_cert: str


class Sprint(_Model):
    """Bundle F — the team's active sprint."""

    number: int
    name: str
    start: str
    end: str
    goal: str


class Okr(_Model):
    id: str
    objective: str
    key_results: list[str]
    progress: float


class CertTarget(_Model):
    vertical: str
    cert: str
    target_quarter: str


class CapacityPolicy(_Model):
    """Target weekly study hours the team allocates per seniority band."""

    target_study_hours_by_seniority: dict[Seniority, int]


class Team(_Model):
    id: str
    name: str
    manager_employee_id: str
    member_employee_ids: list[str]
    sprint: Sprint
    okrs: list[Okr]
    cert_targets: list[CertTarget]
    capacity_policy: CapacityPolicy


class Org(_Model):
    id: str
    name: str
    product: str
    department: str
    teams: list[Team]


class ServiceWeek(_Model):
    id: str
    start: str
    end: str
    weekdays: list[Weekday]
    timezone: str


class ServiceScope(_Model):
    """Honest provenance: which surfaces are Work-IQ-pattern vs adjacent context.

    Real Microsoft Work IQ derives from M365 activity (calendar, meetings, mail,
    files). Profile (HRIS) and team sprint/OKRs (Azure Boards / Viva Goals) are
    adjacent systems — included for demo realism, not claimed to come from Work IQ.
    """

    work_iq_pattern: list[str]
    adjacent_context: list[str]
    note: str


class ServiceInfo(_Model):
    name: str
    pattern: str
    description: str
    principles: list[str]
    scope: ServiceScope
    security_note: str
    disclaimer: str
    schema_version: str
    week: ServiceWeek


class WorkIQDocument(_Model):
    """Root of the synthetic Work IQ data source."""

    service: ServiceInfo
    org: Org
    verticals: list[Vertical]
    personas: list[Persona]


# ── Projected response models (lightweight views for list/aggregate endpoints) ──


class PersonaSummary(_Model):
    """Compact persona row for the roster endpoint."""

    employee_id: str
    codename: str
    team_id: str
    vertical: str
    seniority: Seniority
    role_title: str
    certification: str
    is_manager: bool
    preferred_learning_slot: LearningSlot

    @classmethod
    def of(cls, persona: Persona) -> PersonaSummary:
        return cls(
            employee_id=persona.employee_id,
            codename=persona.codename,
            team_id=persona.team_id,
            vertical=persona.vertical,
            seniority=persona.seniority,
            role_title=persona.role_title,
            certification=persona.certification,
            is_manager=persona.is_manager,
            preferred_learning_slot=persona.preferred_learning_slot,
        )


class Availability(_Model):
    """Derived availability projection (Bundle B) — when this person is reachable/free."""

    employee_id: str
    work_mode: WorkMode
    working_hours: TimeWindow
    working_days: list[Weekday]
    focus_windows: list[TimeWindow]
    on_call: OnCall
    pto_days: list[str]
    weekly_free_capacity_hours: float

    @classmethod
    def of(cls, persona: Persona, weekly_free_capacity_hours: float) -> Availability:
        ctx = persona.work_context
        return cls(
            employee_id=persona.employee_id,
            work_mode=ctx.work_mode,
            working_hours=ctx.working_hours,
            working_days=ctx.working_days,
            focus_windows=ctx.focus_windows,
            on_call=ctx.on_call,
            pto_days=ctx.pto_days,
            weekly_free_capacity_hours=weekly_free_capacity_hours,
        )


class TeamCapacity(_Model):
    """Aggregate-only team capacity view (manager surface — never per-learner detail)."""

    team_id: str
    team_name: str
    member_count: int
    avg_meeting_hours_per_week: float
    avg_focus_hours_per_week: float
    high_meeting_load_count: int
    readiness_distribution: dict[ReadinessStatus, int]
    capacity_policy: CapacityPolicy
