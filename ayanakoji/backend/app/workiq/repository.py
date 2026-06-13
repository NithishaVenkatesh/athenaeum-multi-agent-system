"""Read-only repository over the synthetic Work IQ data source.

Repository pattern (rules/common/patterns.md): callers depend on this typed,
GET-only surface, not on the JSON layout. The document is immutable and parsed
once (``get_repository`` is cached); tests construct a repository from an
in-memory document to stay credential- and filesystem-light.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.workiq.models import (
    DaySchedule,
    LearnerProfile,
    Org,
    Persona,
    PersonaSummary,
    ServiceInfo,
    Team,
    TeamCapacity,
    Vertical,
    Weekday,
    WeekSchedule,
    WorkIQDocument,
    WorkSignals,
)

# app/workiq/repository.py -> app/data/work_iq.json
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "work_iq.json"

# A meeting week above this many hours trips the capacity-reduction rule (§13).
HEAVY_MEETING_THRESHOLD_HOURS = 20.0


class WorkIQRepository:
    """Typed read access to the synthetic org. No mutation, no I/O after load."""

    def __init__(self, document: WorkIQDocument) -> None:
        self._doc = document
        self._by_employee: dict[str, Persona] = {p.employee_id: p for p in document.personas}

    @classmethod
    def from_path(cls, path: Path) -> WorkIQRepository:
        """Load and validate the data source from disk."""
        return cls(WorkIQDocument.model_validate_json(path.read_text(encoding="utf-8")))

    # ── Service / org / catalog ──────────────────────────────────────────────

    def service_info(self) -> ServiceInfo:
        return self._doc.service

    def org(self) -> Org:
        return self._doc.org

    def verticals(self) -> list[Vertical]:
        return list(self._doc.verticals)

    def get_team(self, team_id: str) -> Team | None:
        return next((t for t in self._doc.org.teams if t.id == team_id), None)

    # ── Personas ─────────────────────────────────────────────────────────────

    def list_personas(
        self,
        *,
        vertical: str | None = None,
        seniority: str | None = None,
        team_id: str | None = None,
    ) -> list[Persona]:
        """All personas, optionally filtered. Filters combine with AND."""
        personas = self._doc.personas
        if vertical is not None:
            personas = [p for p in personas if p.vertical == vertical]
        if seniority is not None:
            personas = [p for p in personas if p.seniority == seniority]
        if team_id is not None:
            personas = [p for p in personas if p.team_id == team_id]
        return list(personas)

    def list_persona_summaries(
        self,
        *,
        vertical: str | None = None,
        seniority: str | None = None,
        team_id: str | None = None,
    ) -> list[PersonaSummary]:
        return [
            PersonaSummary.of(p)
            for p in self.list_personas(vertical=vertical, seniority=seniority, team_id=team_id)
        ]

    def get_persona(self, employee_id: str) -> Persona | None:
        return self._by_employee.get(employee_id)

    # ── Granular projections ─────────────────────────────────────────────────

    def get_schedule(self, employee_id: str) -> WeekSchedule | None:
        persona = self.get_persona(employee_id)
        return persona.schedule if persona else None

    def get_day(self, employee_id: str, day: Weekday) -> DaySchedule | None:
        schedule = self.get_schedule(employee_id)
        if schedule is None:
            return None
        return next((d for d in schedule.days if d.day == day), None)

    def get_work_signals(self, employee_id: str) -> WorkSignals | None:
        persona = self.get_persona(employee_id)
        return persona.work_signals if persona else None

    def list_work_signals(self) -> list[WorkSignals]:
        """The Work IQ Dataset 2 surface for the whole org."""
        return [p.work_signals for p in self._doc.personas]

    def get_learning(self, employee_id: str) -> LearnerProfile | None:
        persona = self.get_persona(employee_id)
        return persona.learning if persona else None

    # ── Manager surface (aggregate-only) ─────────────────────────────────────

    def team_capacity(self, team_id: str) -> TeamCapacity | None:
        """Aggregate capacity for a team — never exposes per-learner detail (§14)."""
        team = self.get_team(team_id)
        if team is None:
            return None
        members = self.list_personas(team_id=team_id)
        if not members:
            return None
        meeting = [p.work_signals.meeting_hours_per_week for p in members]
        focus = [p.work_signals.focus_hours_per_week for p in members]
        readiness: Counter[str] = Counter(p.learning.readiness_status for p in members)
        return TeamCapacity(
            team_id=team.id,
            team_name=team.name,
            member_count=len(members),
            avg_meeting_hours_per_week=round(sum(meeting) / len(meeting), 2),
            avg_focus_hours_per_week=round(sum(focus) / len(focus), 2),
            high_meeting_load_count=sum(h > HEAVY_MEETING_THRESHOLD_HOURS for h in meeting),
            readiness_distribution={
                "GO": readiness.get("GO", 0),
                "CONDITIONAL": readiness.get("CONDITIONAL", 0),
                "NOT_YET": readiness.get("NOT_YET", 0),
            },
        )


@lru_cache(maxsize=1)
def get_repository() -> WorkIQRepository:
    """The default repository bound to the committed data source (cached)."""
    return WorkIQRepository.from_path(DATA_PATH)
