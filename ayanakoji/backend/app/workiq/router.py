"""GET-only HTTP surface for the synthetic Work IQ service.

Mirrors Work IQ's "Unified Surface" principle: one read contract over personas,
roles, schedules, and work signals. Every route is read-only — this is a
workplace-intelligence *read* layer, never a system of record. The repository is
injected via ``Depends`` so tests can swap in an in-memory document.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.workiq.models import (
    DaySchedule,
    LearnerProfile,
    Org,
    Persona,
    PersonaSummary,
    Seniority,
    ServiceInfo,
    Team,
    TeamCapacity,
    Vertical,
    Weekday,
    WeekSchedule,
    WorkSignals,
)
from app.workiq.repository import WorkIQRepository, get_repository

RepoDep = Annotated[WorkIQRepository, Depends(get_repository)]

router = APIRouter(prefix="/api/workiq", tags=["workiq"])


def _require[T](value: T | None, *, kind: str, key: str) -> T:
    """Return the value or raise a 404 with a consistent message."""
    if value is None:
        raise HTTPException(status_code=404, detail=f"{kind} '{key}' not found")
    return value


@router.get("", response_model=ServiceInfo, summary="Service descriptor")
def get_service(repo: RepoDep) -> ServiceInfo:
    """Service card: name, Work IQ principles, week window, and synthetic disclaimer."""
    return repo.service_info()


@router.get("/org", response_model=Org, summary="Organization & teams")
def get_org(repo: RepoDep) -> Org:
    return repo.org()


@router.get("/verticals", response_model=list[Vertical], summary="Engineering verticals")
def list_verticals(repo: RepoDep) -> list[Vertical]:
    return repo.verticals()


@router.get("/personas", response_model=list[PersonaSummary], summary="Persona roster")
def list_personas(
    repo: RepoDep,
    vertical: Annotated[str | None, Query(description="Filter by vertical id")] = None,
    seniority: Annotated[Seniority | None, Query(description="Filter by seniority")] = None,
    team_id: Annotated[str | None, Query(description="Filter by team id")] = None,
) -> list[PersonaSummary]:
    """Compact roster; filters combine with AND."""
    return repo.list_persona_summaries(vertical=vertical, seniority=seniority, team_id=team_id)


@router.get("/personas/{employee_id}", response_model=Persona, summary="Full persona")
def get_persona(employee_id: str, repo: RepoDep) -> Persona:
    """Everything about one person: role, cert, work signals, learner profile, schedule."""
    return _require(repo.get_persona(employee_id), kind="persona", key=employee_id)


@router.get(
    "/personas/{employee_id}/schedule",
    response_model=WeekSchedule,
    summary="Full week schedule",
)
def get_schedule(employee_id: str, repo: RepoDep) -> WeekSchedule:
    return _require(repo.get_schedule(employee_id), kind="persona", key=employee_id)


@router.get(
    "/personas/{employee_id}/schedule/{day}",
    response_model=DaySchedule,
    summary="One day's timed blocks",
)
def get_day(employee_id: str, day: Weekday, repo: RepoDep) -> DaySchedule:
    """A single weekday's calendar (``mon``..``fri``) at 30-minute resolution."""
    schedule = _require(repo.get_schedule(employee_id), kind="persona", key=employee_id)
    return _require(
        next((d for d in schedule.days if d.day == day), None),
        kind="day",
        key=f"{employee_id}/{day}",
    )


@router.get(
    "/personas/{employee_id}/signals",
    response_model=WorkSignals,
    summary="Work signals (Work IQ Dataset 2)",
)
def get_signals(employee_id: str, repo: RepoDep) -> WorkSignals:
    return _require(repo.get_work_signals(employee_id), kind="persona", key=employee_id)


@router.get(
    "/personas/{employee_id}/learning",
    response_model=LearnerProfile,
    summary="Learner profile (Dataset 1)",
)
def get_learning(employee_id: str, repo: RepoDep) -> LearnerProfile:
    return _require(repo.get_learning(employee_id), kind="persona", key=employee_id)


@router.get("/work-signals", response_model=list[WorkSignals], summary="All work signals")
def list_work_signals(repo: RepoDep) -> list[WorkSignals]:
    """Org-wide Work IQ Dataset 2 surface — one row per persona."""
    return repo.list_work_signals()


@router.get("/teams/{team_id}", response_model=Team, summary="Team roster")
def get_team(team_id: str, repo: RepoDep) -> Team:
    return _require(repo.get_team(team_id), kind="team", key=team_id)


@router.get(
    "/teams/{team_id}/capacity",
    response_model=TeamCapacity,
    summary="Aggregate team capacity (manager view)",
)
def get_team_capacity(team_id: str, repo: RepoDep) -> TeamCapacity:
    """Aggregate-only capacity: averages + readiness distribution, no per-learner detail."""
    return _require(repo.team_capacity(team_id), kind="team", key=team_id)
