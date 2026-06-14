from __future__ import annotations

from datetime import date

from app.agent.contracts import SkillGateRequestEvent
from app.agent.orchestrator import run_pipeline
from app.agent.state import CourseState


def test_pipeline_emits_skill_gate_in_chosen_state() -> None:
    events = list(
        run_pipeline(
            "build me a study plan",
            persona_id="EMP-001",
            catalog_id="cb-c01",
            skill_source=None,
            skill_scores=None,
            start_date=date(2026, 6, 15),
            course_state=CourseState.CHOSEN,
        )
    )
    assert any(isinstance(e, SkillGateRequestEvent) for e in events)
