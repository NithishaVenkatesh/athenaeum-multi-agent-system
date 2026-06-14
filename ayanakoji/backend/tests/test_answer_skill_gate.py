"""answer_study_plan asks the skill gate before pace, and previews after pace."""

from __future__ import annotations

from datetime import date

from app.agent.answer import answer_study_plan
from app.agent.contracts import Pace
from app.workiq.repository import get_repository

START = date(2026, 6, 15)


def _persona_id() -> str:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    return vega.employee_id


def test_no_skill_source_returns_skill_gate_not_pace() -> None:
    reply = answer_study_plan(
        "build me a plan",
        persona_id=_persona_id(),
        catalog_id="cb-c01",
        taken=[],
        pace=None,
        skill_source=None,
        skill_scores=None,
        start_date=START,
    )
    assert reply.skill_gate is not None
    assert reply.skill_gate.catalog_id == "cb-c01"
    assert reply.pace_request is None
    assert reply.plan is None


def test_skill_done_no_pace_returns_pace_request() -> None:
    reply = answer_study_plan(
        "build me a plan",
        persona_id=_persona_id(),
        catalog_id="cb-c01",
        taken=[],
        pace=None,
        skill_source="assessment",
        skill_scores={"cb-c01-m01": 1.0},
        start_date=START,
    )
    assert reply.skill_gate is None
    assert reply.pace_request is not None
    assert reply.plan is None


def test_skill_and_pace_builds_preview_with_awaiting_approval() -> None:
    reply = answer_study_plan(
        "build me a plan",
        persona_id=_persona_id(),
        catalog_id="cb-c01",
        taken=[],
        pace=Pace.NORMAL,
        skill_source="assessment",
        skill_scores={"cb-c01-m01": 1.0},
        start_date=START,
    )
    assert reply.skill_gate is None and reply.pace_request is None
    assert reply.plan is not None
    assert reply.plan.awaiting_approval is True
