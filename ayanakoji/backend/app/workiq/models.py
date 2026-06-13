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


class DaySchedule(_Model):
    day: Weekday
    date: str
    blocks: list[CalendarBlock]


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
    work_signals: WorkSignals
    learning: LearnerProfile
    schedule: WeekSchedule


class Vertical(_Model):
    id: str
    title: str
    primary_cert: str


class Team(_Model):
    id: str
    name: str
    manager_employee_id: str
    member_employee_ids: list[str]


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


class ServiceInfo(_Model):
    name: str
    pattern: str
    description: str
    principles: list[str]
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


class TeamCapacity(_Model):
    """Aggregate-only team capacity view (manager surface — never per-learner detail)."""

    team_id: str
    team_name: str
    member_count: int
    avg_meeting_hours_per_week: float
    avg_focus_hours_per_week: float
    high_meeting_load_count: int
    readiness_distribution: dict[ReadinessStatus, int]
