"""Tests for the course state machine + grounding guards."""

from __future__ import annotations

from datetime import date

from app.agent.answer import _plan_offline_narration
from app.agent.contracts import Pace, Route
from app.agent.guards import (
    allowed_plan_numbers,
    numbers_in,
    plan_narration_is_grounded,
    ungrounded_numbers,
)
from app.agent.state import CourseState, derive_course_state, transition_note
from app.agent.study_plan import build_study_plan
from app.workiq.repository import get_repository

# ── State machine ──────────────────────────────────────────────────────────────


def test_state_progression() -> None:
    assert (
        derive_course_state(catalog_id=None, pace=None, module_count=0, completed_count=0)
        is CourseState.NEW
    )
    assert (
        derive_course_state(catalog_id="cb-c01", pace=None, module_count=0, completed_count=0)
        is CourseState.CHOSEN
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=0, completed_count=0
        )
        is CourseState.PACED
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=0
        )
        is CourseState.PLANNED
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=2
        )
        is CourseState.IN_PROGRESS
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=4
        )
        is CourseState.COMPLETED
    )


def test_transition_note_explains_the_gate() -> None:
    note = transition_note(CourseState.CHOSEN, Route.STUDY_PLAN)
    assert "ask pace" in note
    assert "chosen" in note


# ── Grounding guards ───────────────────────────────────────────────────────────


def test_numbers_in_normalizes() -> None:
    assert numbers_in("3.0 hours over 5 weeks") == {"3", "5"}


def test_offline_plan_narration_is_grounded() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    assert plan is not None
    narration = _plan_offline_narration(plan)
    # Every number in the deterministic narration traces to the plan.
    assert plan_narration_is_grounded(narration, plan)


def test_guard_catches_fabricated_number() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    assert plan is not None
    bad = "This plan needs 999 hours."  # 999 is not anywhere in the plan
    assert not plan_narration_is_grounded(bad, plan)
    assert "999" in ungrounded_numbers(bad, allowed_plan_numbers(plan))
