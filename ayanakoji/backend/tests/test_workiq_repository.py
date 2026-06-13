"""Unit tests for WorkIQRepository.

Most assertions run against the real committed data source; a tiny in-memory
document exercises edge branches (an empty team) without touching disk.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.workiq.models import WorkIQDocument
from app.workiq.repository import DATA_PATH, WorkIQRepository, get_repository


@pytest.fixture(scope="module")
def repo() -> WorkIQRepository:
    return WorkIQRepository.from_path(DATA_PATH)


# ── Catalog / org ────────────────────────────────────────────────────────────


def test_service_info_and_org(repo: WorkIQRepository) -> None:
    assert repo.service_info().pattern == "Microsoft Work IQ"
    assert repo.org().teams[0].id == "TEAM-A"
    assert len(repo.verticals()) == 5


def test_get_team_found_and_missing(repo: WorkIQRepository) -> None:
    assert repo.get_team("TEAM-A") is not None
    assert repo.get_team("TEAM-NOPE") is None


# ── Persona listing + filters ────────────────────────────────────────────────


def test_list_personas_unfiltered(repo: WorkIQRepository) -> None:
    assert len(repo.list_personas()) == 11


def test_list_personas_filters_combine_with_and(repo: WorkIQRepository) -> None:
    seniors = repo.list_personas(seniority="senior")
    assert len(seniors) == 5
    cloud_senior = repo.list_personas(vertical="cloud-backend", seniority="senior")
    assert [p.codename for p in cloud_senior] == ["Vega"]
    team = repo.list_personas(team_id="TEAM-A")
    assert len(team) == 11
    assert repo.list_personas(vertical="does-not-exist") == []


def test_persona_summaries_project_compact_rows(repo: WorkIQRepository) -> None:
    summaries = repo.list_persona_summaries(seniority="manager")
    assert len(summaries) == 1
    assert summaries[0].is_manager is True
    # Summary must not carry schedule/learner detail (it is a projection).
    assert not hasattr(summaries[0], "schedule")


def test_get_persona_found_and_missing(repo: WorkIQRepository) -> None:
    assert repo.get_persona("EMP-001").codename == "Vega"  # type: ignore[union-attr]
    assert repo.get_persona("EMP-999") is None


# ── Granular projections ─────────────────────────────────────────────────────


def test_get_schedule_and_day(repo: WorkIQRepository) -> None:
    schedule = repo.get_schedule("EMP-001")
    assert schedule is not None
    assert [d.day for d in schedule.days] == ["mon", "tue", "wed", "thu", "fri"]

    wed = repo.get_day("EMP-001", "wed")
    assert wed is not None and wed.day == "wed"
    assert wed.blocks


def test_get_schedule_and_day_missing_persona(repo: WorkIQRepository) -> None:
    assert repo.get_schedule("EMP-999") is None
    assert repo.get_day("EMP-999", "mon") is None


def test_get_signals_and_learning(repo: WorkIQRepository) -> None:
    signals = repo.get_work_signals("EMP-009")
    assert signals is not None and signals.employee_id == "EMP-009"
    learning = repo.get_learning("EMP-009")
    assert learning is not None and learning.learner_id == "L-1009"
    assert repo.get_work_signals("EMP-999") is None
    assert repo.get_learning("EMP-999") is None


def test_list_work_signals_one_row_per_persona(repo: WorkIQRepository) -> None:
    signals = repo.list_work_signals()
    assert len(signals) == 11
    assert {s.employee_id for s in signals} == {p.employee_id for p in repo.list_personas()}


# ── Aggregate (manager) surface ──────────────────────────────────────────────


def test_team_capacity_aggregates(repo: WorkIQRepository) -> None:
    capacity = repo.team_capacity("TEAM-A")
    assert capacity is not None
    assert capacity.member_count == 11
    # Distribution sums back to the member count.
    assert sum(capacity.readiness_distribution.values()) == 11
    assert capacity.high_meeting_load_count >= 3
    # Average is the mean of the per-persona meeting hours.
    expected = round(
        sum(p.work_signals.meeting_hours_per_week for p in repo.list_personas()) / 11, 2
    )
    assert capacity.avg_meeting_hours_per_week == pytest.approx(expected)


def test_team_capacity_missing_team_returns_none(repo: WorkIQRepository) -> None:
    assert repo.team_capacity("TEAM-NOPE") is None


def test_get_repository_is_cached() -> None:
    assert get_repository() is get_repository()


# ── Edge branch: a team that exists but has no members ───────────────────────


def _minimal_block() -> dict[str, Any]:
    return {
        "start": "09:00",
        "end": "10:00",
        "category": "focus",
        "meter": "focus",
        "duration_hours": 1.0,
        "title": "Deep work",
        "collaborative": False,
    }


def _minimal_persona() -> dict[str, Any]:
    return {
        "employee_id": "EMP-001",
        "learner_id": "L-1001",
        "codename": "Vega",
        "team_id": "TEAM-X",
        "vertical": "cloud-backend",
        "seniority": "senior",
        "role_title": "Senior Backend Engineer",
        "certification": "AZ-204",
        "is_manager": False,
        "manager_employee_id": None,
        "reports": [],
        "timezone": "Asia/Kolkata",
        "preferred_learning_slot": "Morning",
        "work_signals": {
            "employee_id": "EMP-001",
            "meeting_hours_per_week": 5.0,
            "focus_hours_per_week": 20.0,
            "preferred_learning_slot": "Morning",
            "collaboration_load": "low",
        },
        "learning": {
            "learner_id": "L-1001",
            "role": "Senior Backend Engineer",
            "certification": "AZ-204",
            "practice_score_avg": 80,
            "hours_studied": 20,
            "exam_outcome": "Pass",
            "target_cert": "AZ-305",
            "recommended_hours": 20,
            "readiness_status": "GO",
        },
        "schedule": {
            "week_id": "2026-W24",
            "days": [{"day": "mon", "date": "2026-06-08", "blocks": [_minimal_block()]}],
        },
    }


def _minimal_document() -> WorkIQDocument:
    return WorkIQDocument.model_validate(
        {
            "service": {
                "name": "Test",
                "pattern": "Microsoft Work IQ",
                "description": "x",
                "principles": ["Unified Surface"],
                "security_note": "x",
                "disclaimer": "synthetic demo",
                "schema_version": "1.0.0",
                "week": {
                    "id": "2026-W24",
                    "start": "2026-06-08",
                    "end": "2026-06-12",
                    "weekdays": ["mon", "tue", "wed", "thu", "fri"],
                    "timezone": "Asia/Kolkata",
                },
            },
            "org": {
                "id": "ORG-X",
                "name": "X",
                "product": "X",
                "department": "X",
                "teams": [
                    {
                        "id": "TEAM-X",
                        "name": "Has members",
                        "manager_employee_id": "EMP-001",
                        "member_employee_ids": ["EMP-001"],
                    },
                    {
                        "id": "TEAM-EMPTY",
                        "name": "No members",
                        "manager_employee_id": "EMP-001",
                        "member_employee_ids": [],
                    },
                ],
            },
            "verticals": [{"id": "cloud-backend", "title": "Cloud", "primary_cert": "AZ-204"}],
            "personas": [_minimal_persona()],
        }
    )


def test_team_capacity_empty_team_returns_none() -> None:
    repo = WorkIQRepository(_minimal_document())
    # Team exists in the org but no personas belong to it.
    assert repo.get_team("TEAM-EMPTY") is not None
    assert repo.team_capacity("TEAM-EMPTY") is None
    # Sanity: the populated team still aggregates.
    assert repo.team_capacity("TEAM-X") is not None
